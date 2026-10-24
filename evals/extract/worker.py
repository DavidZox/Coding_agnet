"""evals/extract/run.py 在臨時的專案副本裡執行這支（cwd＝副本、PYTHONPATH＝副本）：跑一個情境——照技能輸出存檔、提煉一次；
有 recall 的再用 result_recall 追問同一份存檔。結果（回覆原文、秒數、last_tool_summary）寫成 JSON。

    python3 evals/extract/worker.py <case.json> <out.json>     # 模型由環境變數 EVAL_MODEL 指定"""
import json
import os
import sys
import time


def main(case_path, out_path):
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    from agent_core.agent import SkillAgent
    agent = SkillAgent(model=os.environ.get("EVAL_MODEL", "gemma4:26b"))
    agent.current_cwd = os.getcwd()
    agent.set_current_task(case["question"])
    agent.messages.append({"role": "user", "content": case["question"]})
    rec = agent._record_trajectory(case["script"], case["args"], case["text"], agent.current_cwd, "", "")
    res = {"result_id": rec["id"]}
    t0 = time.time()
    try:
        res["summary"] = agent.summarize_tool_result(case["text"], agent.count_tokens(case["text"]), step=case["step"], result_id=rec["id"])
    except Exception as e:   # noqa: BLE001
        res["summary"], res["error"] = "", f"{type(e).__name__}: {e}"
    res["summary_seconds"] = round(time.time() - t0, 1)
    res["last"] = getattr(agent, "last_tool_summary", None)
    if case.get("recall") and not res.get("error"):
        q = case["recall"]
        agent.set_current_task(q)
        agent.messages.append({"role": "user", "content": q})
        t0 = time.time()
        try:
            res["recall"] = agent._result_recall(f'{rec["id"]} "{q}"')
        except Exception as e:   # noqa: BLE001
            res["recall"], res["error"] = "", f"{type(e).__name__}: {e}"
        res["recall_seconds"] = round(time.time() - t0, 1)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
