"""workflow_run：偽技能（同 task_run）——工作流由 harness 的 process 照步驟推進（agent_core/workflow.py 的 WorkflowMixin），判斷點要呼叫模型。
這個檔案只是讓「腳本存在」的檢查與確認關卡（config.GUARDED_SKILLS 的 workflow_run）照常運作；直接執行時說明用法。"""
print("[ERROR] workflow_run 由 harness 執行：在主對話的 action.command 填 scripts/workflow_run_cmd.py、args 填「<工作流名稱> key=value …」"
      "（停在【確認】時填 --continue）。工作流在 skills_system/workflows/，清單見 SKILLS.md〈工作流〉。")
