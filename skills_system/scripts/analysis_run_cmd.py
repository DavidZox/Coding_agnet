"""analysis_run：偽技能（同 task_run、result_recall）——全部由程式做（不呼叫模型），在 harness 的 process 裡做：job 資料夾、
進度推到 Web 右欄、目前的數據同步（agent_core/analysis_job.py 的 AnalysisMixin.analysis_run）。這個檔案只是讓「腳本存在」的檢查照常運作；
直接執行時說明用法。"""
print("[ERROR] analysis_run 由 harness 執行：在主對話的 action.command 填 scripts/analysis_run_cmd.py、args 填 --data <數據> 與使用者的問題。")
