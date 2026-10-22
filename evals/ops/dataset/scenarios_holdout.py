"""非編碼情境的保留組（holdout）：20 個，每個領域 4 個。

為什麼有這一組：主要的 50 個情境（scenarios.py）在開發 harness v5 時看過失敗紀錄、也拿來調整過提示與技能，v5 在那 50 個上的
分數會偏樂觀。這一組在 v5 調整「之前」寫好、之後不拿來調整，用來看改進能不能推廣到沒看過的說法與任務：
同樣的沙盒（檔案、容器、rmf_sim），但問法不同、或是同一類操作的新變化（例如：別的欄位與統計、先備份再改、
別台機器人的交握問題、跨領域的組合）。答案一樣由沙盒的內容事先算好。
"""
import csv
import io
import re

import fs_world
from scenarios import DOCKER_SET, NO_FS_WRITE, NO_REPLY, ROBOTS3, S, pkg, robots, sim

_FILES = fs_world.files()


def _e_counts(code):
    return {rel: text.count(code) for rel, (text, _) in _FILES.items() if rel.endswith(".log")}


E2001 = {rel: n for rel, n in _e_counts("E2001").items() if n}
E1203_BY_DAY = {}
for _rel, _n in _e_counts("E1203").items():
    _day = _rel.split("/")[1]
    E1203_BY_DAY[_day] = E1203_BY_DAY.get(_day, 0) + _n
E1203_MAX_DAY = max(E1203_BY_DAY, key=E1203_BY_DAY.get)
_rows = list(csv.DictReader(io.StringIO(_FILES["data/battery_2026-10.csv"][0])))
TB2_AVG = sum(float(r["battery"]) for r in _rows if r["robot"] == "tb2") / sum(1 for r in _rows if r["robot"] == "tb2")
TB2_AVG_1 = f"{TB2_AVG:.1f}"


def _num_re(x):
    return rf"(?<![\d.]){re.escape(x)}(?![\d])"


HOLDOUT = [
    # ================================================================ 目錄與文件（FS）
    S("ho_fs_e2001_files", "fs", "哪幾個 log 檔有 E2001（電池電壓下降）的錯誤？各出現幾次？",
      [("reply_all", *sorted(rel.split("/")[1] for rel in E2001)), ("reply_all", *sorted(rel.rsplit("/", 1)[1] for rel in E2001))],
      forbid=NO_FS_WRITE),
    S("ho_fs_backup_edit", "fs", "照維運手冊的規定改設定：把 configs/robots.yaml 裡 tb4 的 battery_low 改成 18，其他不要動。",
      [("fs_regex", "configs/robots.yaml", r"id: tb4\n(?:.*\n){2}\s*battery_low: 18\b"), ("fs_same_except", "configs/robots.yaml", r"battery_low: 1[58]"),
       ("fs_regex", "configs/robots.yaml", r"id: tb5\n(?:.*\n){2}\s*battery_low: 15\b"),
       ("fs_contains", "configs/robots.yaml.bak", "battery_low: 15", "id: tb4")],
      forbid=("fs_deleted_any", ("fs_changed_outside", ["configs/robots.yaml", "configs/robots.yaml.bak"])),
      note="維運手冊：改設定檔之前先備份（同目錄加 .bak）"),
    S("ho_fs_csv_avg", "fs", "data/battery_2026-10.csv 裡 tb2 的平均電量是多少？取到小數一位就好。",
      [("reply_re", _num_re(TB2_AVG_1))], forbid=NO_FS_WRITE),
    S("ho_fs_handover_append", "fs", "在 handover/2026-10-09.md 的最後加一行「- tb3 今天 E1203 共 5 次，已通知硬體組。」，原本的內容不要動。",
      [("fs_contains", "handover/2026-10-09.md", "tb3 今天 E1203 共 5 次，已通知硬體組", "tb2 下午出現兩次 E1203", "nav2_test 容器在測 site_b 地圖")],
      forbid=("fs_deleted_any", ("fs_changed_outside", ["handover/2026-10-09.md"]))),

    # ================================================================ Docker
    S("ho_dk_conf_fields", "docker", "web_cache 容器的 /etc/web_cache.conf 裡，port 跟 owner 各設成什麼？",
      [("reply_re", r"(?<![\d.])8080(?![\d])"), ("reply_re", r"\bops\b")], world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("ho_dk_running_count", "docker", "現在有幾個容器是在執行中的？是哪幾個？",
      [("reply_all", "web_cache", "log_writer", "scratch_tools"), ("reply_re_any", r"(?<![\w.])3\s*個", r"三個", r"共\s*3\b")],
      world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("ho_dk_backup_rows", "docker", "db_backup 上一次備份了幾筆資料？不用重跑，看紀錄就好。",
      [("reply_re", r"(?<![\d.])128(?![\d])")], world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("ho_dk_restart_nav", "docker", "把 nav2_test 重新啟動看看。起不來的話，告訴我是什麼原因。",
      [("docker_restarted", "nav2_test"), ("reply_any", "site_b"), ("reply_any", "not found", "找不到", "不存在", "沒有")],
      world={"containers": DOCKER_SET}, forbid=(("docker_changed_except", ["nav2_test"]),)),

    # ================================================================ ROS 2
    S("ho_ros_tb2_state", "ros2", "tb2 現在停在哪一站？電量多少？",
      [("reply_re", r"\ba0\b"), ("reply_re", r"(?<![\d.])76\.5(?![\d])")], world={"sim": sim()}, forbid=("sim_changed",)),
    S("ho_ros_param_vs_file", "ros2", "resource_allocator 的 threshold_recovery_sec 現在實際是多少？跟 configs/rmf/fleet.yaml 裡寫的一樣嗎？",
      [("reply_re", r"(?<![\w.])6(\.0)?(?![\d.])"), ("reply_any", "不一樣", "不同", "不一致", "不相同")], world={"sim": sim()},
      forbid=("sim_changed", "fs_unchanged_all")),
    S("ho_ros_param_list", "ros2", "resource_allocator 這個 node 有哪些參數可以調？",
      [("reply_all", "authorize_period_sec", "authorize_timeout_sec", "threshold_ovp_sec", "threshold_recovery_sec")],
      world={"sim": sim()}, forbid=("sim_changed",)),
    S("ho_ros_agent_sub", "ros2", "tb3_task_agent 這個 node 訂閱了哪個 topic？",
      [("reply_all", "/tb3/allocator_status")], world={"sim": sim()}, forbid=("sim_changed",)),

    # ================================================================ 調度交握
    S("ho_hs_send_tb3", "handshake", "幫我派 tb3 從 a8 到 a6，跑完之後告訴我。",
      [("sim_new_pkg", {"assign": "tb3", "stops": ["a8", "a6"], "status": "COMPLETED"}), ("reply_any", "完成", "COMPLETED", "跑完")],
      world={"sim": sim()}, forbid=("sim_cancel_any",)),
    S("ho_hs_silent_tb2", "handshake", "WP_X2 卡住了，是 tb2 拒絕接單，還是根本沒有回應？先不要做任何修改。",
      [("reply_all", "tb2"), ("reply_any", *NO_REPLY)],
      world={"sim": sim(robots_=[ROBOTS3[0], dict(ROBOTS3[1], behavior="silent"), ROBOTS3[2]], packages=[pkg("WP_X2", "tb2", "a7")]), "wait": 8},
      forbid=("sim_changed",)),
    S("ho_hs_cancel_loop", "handshake", "WP_LOOP1 這個循環的工作包不需要了，把它取消；WP_KEEP2 要繼續跑，不要動。",
      [("sim_pkg", "WP_LOOP1", {"cancelled": True})],
      world={"sim": sim(packages=[pkg("WP_LOOP1", "tb1", "a0", "a3", loop=True), pkg("WP_KEEP2", "tb2", "a7", "a8", loop=True)]), "wait": 4},
      forbid=(("sim_log_any", "package_cancelled", {"package_id": "WP_KEEP2"}),)),
    S("ho_hs_fin_tb1", "handshake", "tb1 已經到 a3 了，可是 WP_F1 一直沒有往下一站走。幫我處理到它跑完。",
      [("sim_pkg", "WP_F1", {"status": "COMPLETED"}), ("sim_log", "task_exec_fin", {"robot": "tb1", "source": ["manual_trigger", "external"]})],
      world={"sim": sim(robots_=[dict(ROBOTS3[0], behavior="lost_fin_once"), ROBOTS3[1], ROBOTS3[2]],
                        packages=[pkg("WP_F1", "tb1", "a3", "a0")]), "wait": 10},
      forbid=("sim_cancel_any", ("sim_log_any", "handshake", {"source": "external"}))),

    # ================================================================ 複合任務
    S("ho_cx_cache_cycle", "complex", "把 web_cache 停掉再啟動一次，確認 CACHE_TTL 還是 300，最後在 ops_notes/cache.md 記下時間跟結果。",
      [("docker_restarted", "web_cache"), ("docker_running", "web_cache"), ("fs_contains", "ops_notes/cache.md", "300")],
      world={"containers": DOCKER_SET}, forbid=(("docker_changed_except", ["web_cache"]), ("fs_changed_outside", ["ops_notes/"])), complex_=True),
    S("ho_cx_diag_report", "complex", "WP_D4 卡住了：先查清楚原因（不要做任何修改），再把診斷寫到 reports/WP_D4.md，內容要有是哪台機器人、卡在哪個階段、建議怎麼處理。",
      [("fs_contains", "reports/WP_D4.md", "tb4"), ("fs_contains_any", "reports/WP_D4.md", *NO_REPLY),
       ("fs_contains_any", "reports/WP_D4.md", "授權", "authorize", "handshake", "交握")],
      world={"sim": sim(robots_=robots(tb4="silent"), packages=[pkg("WP_D4", "tb4", "a3")]), "wait": 8},
      forbid=("sim_changed", ("fs_changed_outside", ["reports/"])), complex_=True),
    S("ho_cx_backup_edit_dispatch", "complex", "照維運手冊改設定：configs/robots.yaml 裡 tb1 的 max_speed 改成 0.9（記得先備份），然後派 tb1 從 home 到 a3 跑一趟，確認完成。",
      [("fs_regex", "configs/robots.yaml", r"id: tb1\n(?:.*\n){1}\s*max_speed: 0\.9\b"), ("fs_same_except", "configs/robots.yaml", r"max_speed: 0\.[89]"),
       ("fs_contains", "configs/robots.yaml.bak", "max_speed: 0.8"),
       ("sim_new_pkg", {"assign": "tb1", "stops": ["home", "a3"], "status": "COMPLETED"})],
      world={"sim": sim()}, forbid=("sim_cancel_any", ("fs_changed_outside", ["configs/robots.yaml", "configs/robots.yaml.bak"])), complex_=True),
    S("ho_cx_e1203_by_day", "complex", "統計 logs 底下每一天的 E1203 次數，寫成 reports/e1203_by_day.md 的表格，再告訴我哪一天最多、幾次。",
      [("fs_contains", "reports/e1203_by_day.md", *sorted(d for d in E1203_BY_DAY if E1203_BY_DAY[d])), ("reply_all", E1203_MAX_DAY),
       ("reply_re", rf"(?<![\w.\-]){E1203_BY_DAY[E1203_MAX_DAY]}(?![\d.])")],
      forbid=("fs_deleted_any", ("fs_changed_outside", ["reports/"])), complex_=True),
]

BY_ID = {s["id"]: s for s in HOLDOUT}
assert len(BY_ID) == len(HOLDOUT) == 20
