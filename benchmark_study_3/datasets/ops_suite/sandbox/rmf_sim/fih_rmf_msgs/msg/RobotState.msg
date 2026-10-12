# 機器人完整狀態，發布於 /{robot_id}/robot_state，取代原本手動組的 JSON 字串
# 由 amr_base_sw RobotStateBroadcaster 發佈，registry/supervisor/dispatcher/adapter/predictor 等節點訂閱使用

string robot_id
int32 priority
fih_rmf_msgs/CurrentState current_state
fih_rmf_msgs/Sequence sequence
