# 單站任務，發布於 /incoming_tasks，取代原本逗號分隔的一行文字（task_id,task_type,level,weight,assign_amr,station）。
# orchestrtor 每個週期，每個執行中的工作包最多派一站；distribute 訂閱，挑選機器人並授權。

string task_id      # orchestrtor 的 item_id："{package_id}::{iteration}::{station_index}::{run_id}-{seq}"（run_id：orchestrtor 每次 configure 取的 8 個 16 進位字元）
string task_type    # 照抄工作包的 task_type
string level        # 照抄工作包的 level
int64 weight        # 照抄工作包的 weight；distribute 只採用大於 0 的值
string assign_amr   # 指定的機器人；空字串（或只有空白）表示不指定，由 distribute 自動配對
string station      # 目標站點；空字串（或只有空白）時 distribute 授權填 "none"
