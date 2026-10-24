"""task_run：偽技能（同 workflow_run）——任務引擎在 harness 的 process 裡規劃、派 worker、檢查（agent_core/task_engine.py 的 TaskMixin）。
這個檔案只是讓「腳本存在」的檢查與確認關卡（config.GUARDED_SKILLS 的 task_run）照常運作；直接執行時說明用法。"""
print("[ERROR] task_run 由 harness 執行：在主對話的 action.command 填 scripts/task_run_cmd.py、args 填使用者的原話"
      "（停下來等確認的任務填 --continue）。")
