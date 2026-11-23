"""評測的 worker（evals/chat/worker.py、evals/ops/worker.py）共用：主模型「交辦」的那一步怎麼收尾、怎麼記。

- 確認關卡（領域 session 碰到會改狀態的工具）照情境的 guard 回答（approve 同意、deny 不同意），跟主對話的確認關卡一樣算進 guards。
- 記成 tool_calls：交辦一筆（skill＝domain_session，附子目標、項目、選過的領域、領域 session 的狀態、工作編號、交辦的結果 #編號），
  領域 session 的每一步各一筆（via＝domain_session；工具附參數，有骨架的技能附參數的值），有骨架的技能再把骨架裡執行的工具各記一筆
  （via＝那個技能）——情境的「用了哪個工具」照樣看得到。交辦沒過核對（[ERROR]）時只有交辦那一筆、狀態 ERROR。
- 依報告回答：這一步的 answers 與核對的結果記進那一步（record_answers）；最後的回答換成程式照項目排好的那一份（finalize：
  使用者看到的就是它，評測照它計分）。"""
import os
import shlex

from agent_core.config import DOMAIN_JOBS_DIRNAME
from agent_core.jobstore import JobStore


def settle(agent, parsed, result, turn, guard="approve"):
    """領域 session 停在確認關卡：照情境的 guard 回答（算進 guards）。回傳最後的結果。"""
    while agent.domain_pending:
        p = agent.domain_pending
        turn.setdefault("domain_asks", []).append(p["question"])
        if isinstance(turn.get("guards"), list):         # 主對話的評測記每一次的關卡；維運記次數
            turn["guards"].append({"question": p["question"], "via": "domain_session"})
        else:
            turn["guards"] = turn.get("guards", 0) + 1
        result = agent.answer_domain("是" if guard == "approve" else "否")
        result = result if result is not None else ""
    return result


def calls(agent, parsed, result):
    """交辦的這一步 → tool_calls 的紀錄。"""
    task = parsed["action"]["task"]
    status = "ERROR" if result.lstrip().startswith(("[ERROR]", "[DENIED]")) else "PASS"
    entry = {"script": None, "skill": "domain_session", "domain": "domain_session", "goal": task.get("goal", ""),
             "items": task.get("items") or [], "args": [task.get("goal", "")] + list(task.get("items") or []), "status": status, "result_id": None}
    tasks = agent._domain_turn["tasks"]
    d = tasks[-1] if status == "PASS" and tasks and tasks[-1]["key"] == [task.get("goal", ""), task.get("items") or []] else None
    job = JobStore(os.path.join(agent.script_dir, "logs", DOMAIN_JOBS_DIRNAME)).load(d["job"]) if d and d.get("job") else None
    if not job:
        return [entry]
    entry.update(result_id=d.get("result_id"), job=job["id"], session_status=job["status"], domains=list(job["domains"]),
                 picks=[p["domains"] for p in job["picks"]], steps=len(job["steps"]), turns=job["turns"], forms=job["forms"])
    out = [entry]
    for st in job["steps"]:
        args = ([str(v["value"]) if not isinstance(v["value"], list) else "、".join(map(str, v["value"])) for v in st["params"].values()]
                if st["kind"] == "composite" else _split(st["args"]))
        out.append({"script": None, "skill": st["skill"], "via": "domain_session", "kind": st["kind"], "args": args, "status": st["status"],
                    "head": st["head"], "result_ids": st["result_ids"], "summarized": st.get("summarized", False)})
        for o in (st.get("composite") or {}).get("outputs") or []:
            out.append({"script": None, "skill": o["tool"], "via": st["skill"], "args": o["args"], "status": o["state"], "result_id": o["result_id"]})
    return out


def _split(args):
    try:
        return shlex.split(args)
    except ValueError:
        return [args] if args else []


def record_answers(agent, parsed, turn):
    """依報告回答的那一步：answers 與沒過核對的項目記進 turn 的最後一步（不是這種回答就不記）。"""
    if parsed.get("action") or not agent.domain_items():
        return
    turn["steps"][-1].update(answers=parsed.get("answers") or [],
                             answer_problems={str(k): v for k, v in agent._answer_problems(parsed).items()})


def finalize(agent, parsed, turn):
    """回合結束時：依報告回答的話，回傳程式照項目排好的回答（也寫進最後一步的 reply）；不是就回 None。"""
    rendered = agent.domain_render(parsed)
    if rendered is not None:
        turn["steps"][-1]["reply"] = rendered
    return rendered
