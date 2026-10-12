# 機器人即時姿態與感測狀態，為 RobotState.msg 的巢狀欄位
# 對應原始 JSON：current_state 物件（來自 amr_base_sw RobotStateBroadcaster._publish_state）
# distance_to_target 原始 JSON 可能為 null（尚無目標時），故另加 has_distance_to_target 旗標表示是否有值

float64 x
float64 y
float64 theta
float64 v
float64 omega
float64 sim_timestamp
string current_edge
string target_id
bool is_arrived
float64 distance_to_target
bool has_distance_to_target
float64 battery_level
bool is_charging
