# Resource Allocator 送給指定機器人的指令，取代原本手動組的 JSON 字串：
#   confirm:   {"command": "confirm",   "data": {"task_id"}}
#   authorize: {"command": "authorize", "data": {"task_id", "type", "action", "station"}}
# confirm/authorize 共用同一個 topic 與同一個訊息型別，用 command 欄位區分；
# confirm 只會用到 command/task_id，其餘欄位維持預設空字串。

string command
string task_id
string type
string action
string station
