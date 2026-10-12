"""非編碼情境的檔案沙盒：模擬機器人維運的工作目錄（設定檔、log、地圖、文件、資料、範本、交班紀錄）。
每個情境開始前重建一份（內容與修改時間固定，答案可以事先算好），agent 的工作目錄就是它的根目錄。"""
import csv
import io
import os
import random
import time

BASE_TS = time.mktime((2026, 10, 10, 9, 50, 0, 0, 0, -1))   # 「現在」＝2026-10-10 09:50
URLS = {"web_console": "http://localhost:8020", "manual_trigger": "http://localhost:8002"}   # 評測時換成沙盒的位址（build 的 urls）
SEED = 20261010

ROBOTS_YAML = """# 機隊設定（調度系統與導航共用）
robots:
  - id: tb1
    model: tinyRobot
    max_speed: 0.8
    battery_low: 20
    home: home
  - id: tb2
    model: tinyRobot
    max_speed: 0.7
    battery_low: 20
    home: a0
  - id: tb3
    model: tinyRobot
    max_speed: 0.55
    battery_low: 25
    home: a8
  - id: tb4
    model: deliveryBot
    max_speed: 1.0
    battery_low: 15
    home: a4
  - id: tb5
    model: deliveryBot
    max_speed: 1.0
    battery_low: 15
    home: a6
"""

NAV_PARAMS = """controller_server:
  ros__parameters:
    controller_frequency: 20.0
    min_x_velocity_threshold: 0.001
    FollowPath:
      plugin: "dwb_core::DWBLocalPlanner"
      min_vel_x: 0.0
      max_vel_x: 0.5
      max_vel_theta: 1.0
      acc_lim_x: 2.5
      decel_lim_x: -2.5
local_costmap:
  local_costmap:
    ros__parameters:
      update_frequency: 5.0
      resolution: 0.05
      inflation_radius: 0.55
"""

NAV_PARAMS_BACKUP = NAV_PARAMS.replace("controller_frequency: 20.0", "controller_frequency: 10.0").replace("max_vel_x: 0.5", "max_vel_x: 0.35")

HANDSHAKE_RULES = """# 派工交握規則（機器人端 TaskAgent）

distribute 每 0.5 秒對選中的機器人發 `/{rid}/allocator_status`（authorize），機器人回 `/{rid}/handshake_states`（is_authored：yes／no）。
看到 yes 之後 distribute 發 confirm；機器人做完發 `/{rid}/task_exec_fin`，orchestrtor 收到才派下一站。

| 規則 | 內容 |
|---|---|
| R1 | 每收到一則 authorize 就回一則 HandshakeState；剛接受、執行中、已完成的任務回 yes，其他（忙碌、站點無效、定位異常）回 no |
| R2 | 除了 R1 之外不要主動發 HandshakeState，尤其不要在轉成 IDLE 時發 no——任務瞬間完成時，no 會蓋掉 yes，造成無限重送 |
| R3 | 記住最近完成的 task_id；再收到已完成任務的 authorize 時回 yes 並補發 task_exec_fin，不要重新執行 |
| R4 | 先驗證再回 yes：要是 IDLE、站點存在、起點已知 |
| R5 | task_exec_fin 的 task_id 要逐字等於 authorize 的 task_id；完成後在有限時間內重送 |
| R6 | confirm 不需要回應 |

授權 10 秒內沒看到 yes，任務退回佇列並進 OverPending 冷卻，之後再重送。
"""

OPS_MANUAL = """# 維運手冊（節錄）

## 1. 工作包卡在某一站
1. 用 workpackage_status 看目前工作項（item id）與機器人。
2. 機器人已經到站、但工作包沒有前進 → 多半是 task_exec_fin 遺失。用 manual_trigger（位址見 configs/rmf/fleet.yaml）的
   `POST /batch_task_exec_fin`，body `[{"robot_name": "tb2", "task_id": "<item id>"}]` 補發一次。
3. 機器人沒有回應授權（沒有 handshake_states）→ TaskAgent 沒在跑，**不要**手動回 yes，回報給機器人端處理。

## 2. 容器
- 容器停掉時先看 `docker logs`，找到原因再決定要不要重啟。
- 沒有交代的容器不要動。

## 3. 設定檔
- 改設定檔之前先備份（同目錄加 .bak），改完說明改了哪一行。
"""


def battery_csv():
    rng = random.Random(SEED)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["timestamp", "robot", "battery", "temperature"])
    start = time.mktime((2026, 10, 1, 0, 0, 0, 0, 0, -1))
    levels = {"tb1": 95.0, "tb2": 90.0, "tb3": 88.0, "tb4": 97.0, "tb5": 93.0}
    for i in range(452):                                     # 10/01 00:00 ～ 10/10 09:30（「現在」之前）
        ts = start + i * 1800
        for rid in levels:
            levels[rid] -= rng.uniform(0.2, 1.6)
            if levels[rid] < 18 + rng.uniform(0, 8):
                levels[rid] = 96.0 - rng.uniform(0, 3)
            temp = round(31 + rng.uniform(-2, 6) + (6.5 if (rid == "tb4" and i == 333) else 0), 1)
            w.writerow([time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)), rid, round(levels[rid], 1), temp])
    return out.getvalue()


def robot_log(rid, day, n_e1203, n_e2001, start_hour):
    rng = random.Random(f"{rid}{day}")
    lines = []
    t = time.mktime(tuple(int(x) for x in day.split("-")) + (start_hour, 0, 0, 0, 0, -1))
    errors = sorted(rng.sample(range(5, 120), n_e1203 + n_e2001))
    kinds = ["E1203"] * n_e1203 + ["E2001"] * n_e2001
    rng.shuffle(kinds)
    err_at = dict(zip(errors, kinds))
    for i in range(125):
        t += rng.randint(3, 25)
        stamp = time.strftime("%H:%M:%S", time.localtime(t))
        if i in err_at:
            if err_at[i] == "E1203":
                lines.append(f"{day} {stamp} [ERROR] {rid} E1203 lidar timeout on /scan (no data for 1.2s)")
            else:
                lines.append(f"{day} {stamp} [ERROR] {rid} E2001 battery voltage drop detected")
        else:
            lines.append(f"{day} {stamp} [INFO] {rid} heartbeat ok, pose=({round(rng.uniform(0, 6), 2)}, {round(rng.uniform(0, 2), 2)})")
    return "\n".join(lines) + "\n"


def files():
    """回傳 {相對路徑: (內容, 修改時間)}。"""
    f = {}

    def put(rel, text, minutes_ago):
        f[rel] = (text, BASE_TS - minutes_ago * 60)

    put("README.md", "# 機器人維運工作區\n\n- configs/：機隊、導航、調度設定\n- logs/：每天每台機器人的 log（logs/<日期>/robot_<id>.log）\n"
        "- maps/：地圖\n- docs/：手冊與規則\n- data/：量測資料\n- templates/：任務範本\n- handover/：交班紀錄\n", 6000)
    put("configs/robots.yaml", ROBOTS_YAML, 3000)
    put("configs/nav/nav_params.yaml", NAV_PARAMS, 1500)
    put("configs/nav/nav_params.backup.yaml", NAV_PARAMS_BACKUP, 9000)
    put("configs/rmf/fleet.yaml", "fleet_name: tinyRobot\n# 調度系統的端點（這個環境的位址）\n"
        f"web_console_url: {URLS['web_console']}\nmanual_trigger_url: {URLS['manual_trigger']}\n"
        "authorize_timeout_sec: 10\nthreshold_recovery_sec: 10\n", 4000)
    logs = [("tb1", "2026-09-28", 0, 0, 8, 17000), ("tb2", "2026-09-28", 1, 0, 8, 16990), ("tb1", "2026-10-05", 0, 1, 8, 7000),
            ("tb2", "2026-10-09", 2, 0, 8, 1500), ("tb1", "2026-10-10", 1, 0, 7, 40), ("tb3", "2026-10-10", 5, 1, 7, 8)]
    for rid, day, e1, e2, hour, ago in logs:
        put(f"logs/{day}/robot_{rid}.log", robot_log(rid, day, e1, e2, hour), ago)
    put("logs/archive/README.md", "舊的 log 移到這裡（依日期資料夾）。\n", 20000)
    put("maps/site_a.yaml", "image: site_a.pgm\nresolution: 0.05\norigin: [-10.0, -10.0, 0.0]\noccupied_thresh: 0.65\nfree_thresh: 0.196\n", 30000)
    put("maps/README.md", "目前只有 site_a；site_b 的地圖還沒建。\n", 30000)
    put("docs/handshake_rules.md", HANDSHAKE_RULES, 5000)
    put("docs/ops_manual.md", OPS_MANUAL, 5000)
    put("data/battery_2026-10.csv", battery_csv(), 100)
    put("templates/mission_template/mission.yaml", "name: MISSION_NAME\nrobot: tb1\nstops:\n  - home\n  - a3\nloop: false\n", 20000)
    put("templates/mission_template/README.md", "# MISSION_NAME\n\n任務說明：\n", 20000)
    put("handover/2026-10-09.md", "# 交班 2026-10-09\n\n- tb2 下午出現兩次 E1203（雷達逾時），重開後正常。\n- nav2_test 容器在測 site_b 地圖。\n", 1300)
    return f


def build(root, extra=None, urls=None):
    if urls:
        URLS.update({k: v for k, v in urls.items() if k in URLS})
    os.makedirs(root, exist_ok=True)
    allf = files()
    for rel, (text, ts) in list(allf.items()) + [(k, (v, BASE_TS - 60)) for k, v in (extra or {}).items()]:
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.utime(p, (ts, ts))
    for dp, dns, fns in os.walk(root, topdown=False):            # 目錄的修改時間也固定（list_dir --newest 看的是檔案）
        os.utime(dp, (BASE_TS - 60, BASE_TS - 60))
    return root


def facts():
    """情境的正確答案（從同樣的內容算出來）。"""
    allf = files()
    out = {}
    newest = max((rel for rel in allf if rel.startswith("logs/") and rel.endswith(".log")), key=lambda r: allf[r][1])
    out["newest_log"] = newest
    text = allf[newest][0]
    e1203 = [ln for ln in text.splitlines() if "E1203" in ln]
    out["newest_e1203_count"] = len(e1203)
    out["newest_e1203_last_time"] = e1203[-1].split()[1] if e1203 else None
    counts = {rel: allf[rel][0].count("E1203") for rel in allf if rel.endswith(".log")}
    out["e1203_total"] = sum(counts.values())
    out["e1203_max_file"] = max(counts, key=counts.get)
    rows = list(csv.DictReader(io.StringIO(allf["data/battery_2026-10.csv"][0])))
    mins = {}
    for r in rows:
        b = float(r["battery"])
        if r["robot"] not in mins or b < mins[r["robot"]][0]:
            mins[r["robot"]] = (b, r["timestamp"])
    out["battery_min"] = mins
    hot = max(rows, key=lambda r: float(r["temperature"]))
    out["temp_max"] = (float(hot["temperature"]), hot["robot"], hot["timestamp"])
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(facts(), ensure_ascii=False, indent=1))
