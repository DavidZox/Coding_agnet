"""evals/workflow/sandbox.py 在臨時的 harness 副本裡呼叫：直接執行一個工作流（不經過主對話；判斷點用真模型、技能在沙盒裡真的執行）。
走的是不用互動的入口（agent_core/workflow_cmd.run_headless，同 Agent_Runner.py --workflow … --yes＝之後心跳定期跑工作流的路）：
確認關卡、dispatch、存檔都跟對話裡執行的一樣，事先核准（--yes）。

    python3 evals/workflow/sandbox_worker.py <case.json> <out.json>
環境變數同 evals/ops/worker.py：EVAL_MODEL、OPS_FS_ROOT（檔案沙盒＝工作目錄）、DOCKER_HOST、RMF_WEB_CONSOLE_URL、RMF_MANUAL_TRIGGER_URL。"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        case = json.load(f)
    from agent_core.agent import SkillAgent
    agent = SkillAgent(model=os.environ.get("EVAL_MODEL", "gemma4:26b"))
    agent.reset_conversation()
    agent.current_cwd = os.environ["OPS_FS_ROOT"]
    from agent_core import workflow_cmd
    t0 = time.time()
    code, report = workflow_cmd.run_headless(case["call"], yes=True, agent=agent)
    out = {"report": report, "exit_code": code, "seconds": round(time.time() - t0, 1)}
    job = agent._workflow_store().load(agent.last_workflow_job) if agent.last_workflow_job else None
    out["status"] = (job or {}).get("status")
    out["model_calls"] = (job or {}).get("model_calls")
    out["job_id"] = (job or {}).get("id")
    out["steps"] = {k: {x: v.get(x) for x in ("status", "values", "branch", "decided_by", "why", "head")} for k, v in ((job or {}).get("steps") or {}).items()}
    out["tool_calls"] = [{"script": r.get("script"), "skill": r.get("skill"), "args": r.get("args"), "status": r.get("status"),
                          "head": r.get("output_head")} for r in agent.trajectory if r.get("kind") == "exec"]
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
