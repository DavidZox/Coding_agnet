# 機器人當前任務序列資訊，為 RobotState.msg 的巢狀欄位
# 對應原始 JSON：sequence 物件（來自 amr_base_sw RobotStateBroadcaster._publish_state）
# state 為字串列舉："running" | "standby" | "fail"

string robot_name
string[] workstations
int32 priority
string state
int64 timestamp
