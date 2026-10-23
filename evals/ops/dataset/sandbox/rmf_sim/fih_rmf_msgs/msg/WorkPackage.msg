# 網頁送出的多站點工作包，發布於 /incoming_work_packages，取代原本 JSON 物件字串。
# web_console 收到 POST /api/send_tasks 時，每個工作包發一則；orchestrtor 訂閱，逐站拆成 /incoming_tasks。

string task_id        # 工作包 id（orchestrtor 的 package_id）；網頁空白時填 "T-AUTO"
string task_type      # 預設 "regular"；網頁選單有 regular、charge、park
string level          # 預設 "normal"；網頁選單有 normal、middle、emergency
int64 weight          # 預設 0；原 JSON 是 null 時為 0
string assign_amr     # 指定的機器人；網頁預設 "tb1"
bool loop             # 跑完全部站點後是否從頭循環
int64 loop_count      # 循環幾輪；has_loop_count 為 false 時無意義
bool has_loop_count   # 原 JSON 的 loop_count 是 null（循環到手動刪除）時為 false
fih_rmf_msgs/WorkPackageStop[] stops
