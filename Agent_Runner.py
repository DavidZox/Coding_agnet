"""CLI 入口：python3 Agent_Runner.py。實作在 agent_core/（見 doc/架構說明.md）。
不用互動執行一次工作流（心跳、排程）：python3 Agent_Runner.py --workflow <名稱> key=value … [--yes]（見 agent_core/workflow_cmd.py）。"""
import sys

from agent_core.cli import main

if __name__ == "__main__":
    if "--workflow" in sys.argv[1:]:
        from agent_core.workflow_cmd import main_headless
        sys.exit(main_headless(sys.argv[1:]))
    main()
