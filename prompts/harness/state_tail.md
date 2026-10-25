動態區（agent_core/prompt.py 的 build_state_tail）：每次呼叫主模型時接在最後一則訊息後面、不寫進對話歷史——目前狀態（工作目錄、
容器、ROS 2 Workspace、目前的數據）、Objective、檢索清單的最新一筆（tool_use_index.md 的 index_pointer）。{名稱} 是程式填的值。

<!-- @objective -->
## CURRENT PRIMARY OBJECTIVE
{objective}
規則：你必須始終以此任務為最高優先級；除非使用者明確清除 objective，不可自行移除或遺忘；上下文過長時優先維持此目標。

<!-- @agent_state -->
## Current Agent State
- CURRENT_WORKING_DIRECTORY: {cwd}
- CURRENT_CONTAINER_DIRECTORY: {container_cwd}
- CURRENT_TARGET_CONTAINER: {target}

<!-- @workspace_ok -->
- CURRENT_ROS2_WORKSPACE: {path}
- ROS2_WORKSPACE_CONTAINER: {container}
- ROS 2 Workspace 已記錄；執行前仍須確認該容器內的 install/setup.bash 存在且可載入。

<!-- @workspace_other -->
- CURRENT_ROS2_WORKSPACE: （目前目標容器為 {target}，已記錄的 Workspace 屬於 {container}，不可直接沿用）

<!-- @workspace_none -->
- CURRENT_ROS2_WORKSPACE: （尚未設定；需要 ROS 2 Workspace 時，先確認容器及路徑）

<!-- @header -->
[harness state]
（以下是系統每次附上的目前狀態，不是使用者說的話；請回應上面那則訊息）

<!-- @analysis_data -->
- CURRENT_ANALYSIS_DATA: {data}

<!-- @analysis_data_none -->
（未設定：數據技能第一次指定數據後會記住；也可以給實驗名稱或 latest）

<!-- @analysis_last_job -->
- LAST_ANALYSIS_JOB: {id}（{status}；報告 logs/{dirname}/{id}/report.md）

<!-- @target_none -->
（未設定：需要容器時先用 docker_containers 查、docker_open 選定）

<!-- @workspace_no_target -->
未設定
