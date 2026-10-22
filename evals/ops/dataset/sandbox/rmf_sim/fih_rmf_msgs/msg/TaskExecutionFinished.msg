# 機器人回報單一 work item 執行完成，發布於 /{robot_id}/task_exec_fin
# 取代 orchestrtor 原本暫時借用 distribute 的 confirm 訊號來判斷完成的過渡期做法：
# 機器人實際執行完 orchestrtor 派工的站點任務後，由機器人端發布這則訊息，
# orchestrtor 訂閱到才會判定該 work item 完成、派下一站。

string task_id
