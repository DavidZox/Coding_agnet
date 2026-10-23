# 刪除卡在 OverPending 佇列的任務的要求，發布於 /cancel_overpending_task，取代原本 std_msgs/String（data 是任務 id）。
# web_console 收到 DELETE /api/overpending_tasks/{id} 時發布；distribute 訂閱，只刪除已在 OverPending 的任務。

string task_id   # 前後的空白會被 distribute 去掉；空字串不處理
