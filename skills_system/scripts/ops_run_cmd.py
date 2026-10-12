"""ops_run：偽技能（同 result_recall）——執行計畫要呼叫模型，在 harness 的 process 裡做（agent_core/ops_job.py 的 OpsMixin.ops_run）。
這個檔案只是讓「腳本存在」的檢查與確認關卡（config.GUARDED_SKILLS 的 ops_run）照常運作；直接執行時說明用法。"""
print("[ERROR] ops_run 由 harness 執行：先用 ops_plan 規劃，再在主對話的 action.command 填 scripts/ops_run_cmd.py（args 留空）。")
