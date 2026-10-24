"""跑一個多步驟維運情境（evals/ops/run.py 在臨時的 harness 副本裡呼叫；不要直接在正式專案目錄執行）。

    python3 evals/ops/worker.py <情境 json> <輸出 json>
環境變數：EVAL_MODEL、OPS_FS_ROOT（檔案沙盒＝agent 的工作目錄）、DOCKER_HOST（沙盒 daemon）、RMF_WEB_CONSOLE_URL（沙盒的調度系統）。

跟 evals/chat/worker.py 一樣比照 CLI 的 auto 模式（工具結果自動加入上下文、連續執行到模型不再下 action），差別是工具都真的執行
（在沙盒裡），確認關卡依情境自動回答。任務引擎（task_run）在主對話的回合裡同步執行：查完停下來等確認時，跟 CLI 一樣不經過模型
直接接著問（take_task_continuation），確認跟其他確認關卡一樣依情境回答；每一回合記下執行過的任務（每一版計畫、每一步的狀態、
worker 的工具呼叫與核對過的事實）。模型呼叫數另外計數：agent.perf_calls 只留最近 200 筆，task_run 一次可能就用掉上百次。"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

MAX_STEPS = 25


def main():
    sc_path, out_path = sys.argv[1], sys.argv[2]
    with open(sc_path, encoding="utf-8") as f:
        sc = json.load(f)
    from agent_core.agent import SkillAgent
    from agent_core.protocol import action_text, tool_result_message
    from agent_core.turn import _content_for_context, after_turn_compression

    agent = SkillAgent(model=os.environ.get("EVAL_MODEL", "gemma4:26b"))
    agent.reset_conversation()
    fs_root = os.environ["OPS_FS_ROOT"]
    agent.current_cwd = fs_root
    all_perf = []                            # 不設上限的模型呼叫紀錄（agent.perf_calls 只留最近 200 筆）
    record = agent._perf_record

    def _perf_record(kind, response, model, wall_ms=None, **extra):
        record(kind, response, model, wall_ms=wall_ms, **extra)
        all_perf.append(agent.last_perf)
    agent._perf_record = _perf_record
    skill_map = agent._script_skill_map()
    started = time.time()
    turns, replies = [], []
    for spec in sc["turns"]:
        t0 = time.time()
        perf_before = len(all_perf)
        task_before = getattr(agent, "task_last", None)
        agent.end_plan_for_new_task()
        agent.set_current_task(spec["user"])
        agent.messages.append({"role": "user", "content": spec["user"]})
        turn = {"user": spec["user"], "steps": [], "tool_calls": [], "guards": 0, "hit_step_limit": False}
        for _ in range(MAX_STEPS):
            parsed = agent.take_task_continuation()      # 任務引擎等確認：同 CLI，不經過模型直接接著問
            if parsed:
                raw = parsed["raw"]
            else:
                raw = agent.ask_ai()
                parsed = agent.parse_reply(raw)
            agent.messages.append({"role": "assistant", "content": raw})
            turn["steps"].append({"thought": parsed["thought"], "reply": parsed["reply"],
                                  "action": action_text(parsed["action"]) if parsed["action"] else None, "valid": parsed["valid"],
                                  "harness": bool(parsed.get("raw"))})
            if parsed["reply"]:
                replies.append(parsed["reply"])
            guard = agent.guard_check(parsed)
            if guard:
                turn["guards"] += 1
                if sc.get("guard", "approve") != "approve":
                    agent.messages.append({"role": "user", "content": tool_result_message(agent.guard_denied_text(guard), parsed["action"])})
                    break
            result = agent.run_tool(parsed, approved=bool(guard))
            if not result:
                claim = agent.claim_without_action(parsed)
                if claim:
                    turn.setdefault("claim_nudges", 0)
                    turn["claim_nudges"] += 1
                    agent.messages.append({"role": "user", "content": claim})
                    continue
                break
            payload = action_text(parsed["action"])
            token = os.path.basename(payload.split()[0]) if payload else ""
            script = agent._normalize_script_name(token)
            is_doc = os.path.exists(os.path.join(agent.tools_dir, (token[:-3] if token.endswith(".md") else token) + ".md"))
            if not is_doc:
                args = agent._parse_script_args(script, payload.split(maxsplit=1)[1] if len(payload.split(maxsplit=1)) > 1 else "")
                turn["tool_calls"].append({"script": script, "skill": skill_map.get(script), "args": args,
                                           "status": "ERROR" if result.lstrip().startswith(("[ERROR]", "[DENIED]")) else "PASS",
                                           "head": result.strip().splitlines()[0][:200] if result.strip() else ""})
            content = _content_for_context(result, agent.count_tokens(result), agent=agent, use_summary=True)
            agent.messages.append({"role": "user", "content": tool_result_message(content, parsed["action"])})
            if agent.stuck:
                turn["stuck"] = agent.stuck
                break
        else:
            turn["hit_step_limit"] = True
        job = getattr(agent, "task_last", None)
        if job is None or job is task_before:
            job = getattr(agent, "task_job", None)        # 停下來等確認、被拒絕的任務也記
            job = job if job is not None and job is not task_before and job.get("status") != "planned" else None
        if job is not None:                               # 這一回合執行過 task_run（只記最後一次）
            turn["task_jobs"] = [{"id": job["id"], "status": job["status"], "model_calls": job.get("model_calls"),
                                  "seconds": job.get("seconds"), "task": job["task"], "replans": job.get("replans"),
                                  "plans": job.get("plans"),
                                  "items": [{k: it.get(k) for k in ("n", "title", "skills", "workflow", "workflow_args", "changes_state",
                                                                    "approved", "check", "status", "attempts", "steps", "summary",
                                                                    "facts", "dropped", "evidence", "calls")} for it in job["items"]]}]
        after_turn_compression(agent, False, lambda text: turn.setdefault("notices", []).append(text))
        perf = all_perf[perf_before:]
        turn["main_calls"] = sum(1 for p in perf if p["kind"] == "main")
        turn["side_calls"] = sum(1 for p in perf if p["kind"] != "main")
        turn["seconds"] = round(time.time() - t0, 1)
        turns.append(turn)
    out = {"scenario": sc["id"], "model": agent.model, "turns": turns, "replies": replies,
           "tool_calls": [c for t in turns for c in t["tool_calls"]], "guards": sum(t["guards"] for t in turns),
           "cwd": os.path.relpath(agent.current_cwd, fs_root) if agent.current_cwd.startswith(fs_root) else agent.current_cwd,
           "seconds": round(time.time() - started, 1), "perf": all_perf,
           "model_calls": len(all_perf)}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
