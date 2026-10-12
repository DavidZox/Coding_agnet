"""跑一個非編碼情境（run.py 在臨時的 harness 副本裡呼叫；不要直接在正式專案目錄執行）。

    python3 evals/ops_suite/worker.py <情境 json> <輸出 json>
環境變數：EVAL_MODEL、OPS_FS_ROOT（檔案沙盒＝agent 的工作目錄）、DOCKER_HOST（沙盒 daemon）、RMF_WEB_CONSOLE_URL（沙盒的調度系統）。

跟 evals/worker.py 一樣比照 CLI 的 auto 模式（工具結果自動加入上下文、連續執行到模型不再下 action），差別是工具都真的執行
（在沙盒裡），確認關卡依情境自動回答。harness 有非編碼的 orchestrator（agent.ops）時，回合結束後等它派出去的工作做完
（計畫自動核准，比照 coding 評測）。"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

MAX_STEPS = 25
OPS_WAIT = 1500


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
    ops = getattr(agent, "ops", None)
    if ops is not None:                      # 非編碼的 orchestrator（v5 起）：評測時自動核准、失敗就跳過
        ops.auto_approve = True
        ops.on_fail = "skip"
    skill_map = agent._script_skill_map()
    started = time.time()
    turns, replies = [], []
    for spec in sc["turns"]:
        t0 = time.time()
        perf_before = len(agent.perf_calls)
        agent.end_plan_for_new_task()
        agent.set_current_task(spec["user"])
        agent.messages.append({"role": "user", "content": spec["user"]})
        turn = {"user": spec["user"], "steps": [], "tool_calls": [], "guards": 0, "hit_step_limit": False}
        for _ in range(MAX_STEPS):
            raw = agent.ask_ai()
            parsed = agent.parse_reply(raw)
            agent.messages.append({"role": "assistant", "content": raw})
            turn["steps"].append({"thought": parsed["thought"], "reply": parsed["reply"],
                                  "action": action_text(parsed["action"]) if parsed["action"] else None, "valid": parsed["valid"]})
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
        if ops is not None:                  # 主對話把工作交給 orchestrator 了：等它做完，報告交還給主對話
            deadline = time.time() + OPS_WAIT
            while ops.busy() and time.time() < deadline:
                time.sleep(1)
            for job in ops.drain_finished():
                turn.setdefault("ops_jobs", []).append(job)
                if job.get("report"):
                    replies.append(job["report"])
        after_turn_compression(agent, False, lambda text: turn.setdefault("notices", []).append(text))
        perf = agent.perf_calls[perf_before:]
        turn["main_calls"] = sum(1 for p in perf if p["kind"] == "main")
        turn["side_calls"] = sum(1 for p in perf if p["kind"] != "main")
        turn["seconds"] = round(time.time() - t0, 1)
        turns.append(turn)
    out = {"scenario": sc["id"], "model": agent.model, "turns": turns, "replies": replies,
           "tool_calls": [c for t in turns for c in t["tool_calls"]], "guards": sum(t["guards"] for t in turns),
           "cwd": os.path.relpath(agent.current_cwd, fs_root) if agent.current_cwd.startswith(fs_root) else agent.current_cwd,
           "seconds": round(time.time() - started, 1), "perf": agent.perf_calls,
           "model_calls": len(agent.perf_calls)}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
