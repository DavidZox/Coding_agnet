# 刪除工作包的要求，發布於 /cancel_work_package，取代原本 std_msgs/String（data 是工作包 id）。
# web_console 收到 DELETE /api/work_packages/{id} 時發布；orchestrtor 訂閱，停止派工並從清單移除。

string package_id   # 前後的空白會被 orchestrtor 去掉；空字串不處理
