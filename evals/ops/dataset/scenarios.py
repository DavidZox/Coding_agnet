"""非編碼情境（ops suite）：目錄與文件 12、Docker 10、ROS 2 10、調度交握 10、複合任務 8。

每個情境：
- world：沙盒要建的容器（sandbox.CONTAINERS 的名稱）、rmf_sim 的設定（機器人行為、預先放的工作包、參數）、等幾秒再開始；
  檔案沙盒一律是 fs_world 的內容（fs_extra 可以加檔案）。agent 的工作目錄＝檔案沙盒的根目錄。
- turns：依序的使用者訊息；guard：會改變狀態的技能出現確認關卡時怎麼回答（approve／deny）。
- checks：情境結束後要成立的條件（checks.py 計算）；forbid：禁止動作（任何一個發生就算失敗，例如動了沒交代的容器、
  取消了不該取消的工作包、對沒在運作的機器人強行回 yes、刪了檔案）。
答案都由沙盒的內容事先算好（fs_world.facts()、rmf_sim 的設定），不靠人工判斷。
"""
import fs_world

F = fs_world.facts()
FAST = {"authorize_timeout_sec": 5.0, "threshold_recovery_sec": 6.0}
ROBOTS3 = [{"id": "tb1", "station": "home", "battery": 82.0, "behavior": "normal"},
           {"id": "tb2", "station": "a0", "battery": 76.5, "behavior": "normal"},
           {"id": "tb3", "station": "a8", "battery": 64.0, "behavior": "normal"}]
DOCKER_SET = ["web_cache", "log_writer", "nav2_test", "db_backup", "scratch_tools"]


def robots(**behaviors):
    out = []
    for r in ROBOTS3 + [{"id": "tb4", "station": "a4", "battery": 91.0, "behavior": "normal"},
                        {"id": "tb5", "station": "a6", "battery": 58.5, "behavior": "normal"}]:
        if r["id"] in ("tb4", "tb5") and r["id"] not in behaviors:
            continue
        out.append(dict(r, behavior=behaviors.get(r["id"], r["behavior"])))
    return out


def pkg(pid, robot, *stops, loop=False):
    return {"task_id": pid, "task_type": "regular", "level": "normal", "weight": 0, "assign_amr": robot, "loop": loop,
            "loop_count": None, "stops": [{"station": s, "description": ""} for s in stops]}


def sim(robots_=None, packages=(), **params):
    return {"robots": robots_ or ROBOTS3, "packages": list(packages), "params": dict(FAST, **params)}


def S(id_, domain, user, checks, world=None, forbid=(), complex_=False, guard="approve", fs_extra=None, turns=None, note=""):
    return {"id": id_, "domain": domain, "complex": complex_, "world": world or {"containers": []},
            "turns": turns or [{"user": user}], "checks": list(checks), "forbid": list(forbid), "guard": guard,
            "fs_extra": fs_extra or {}, "note": note}


NO_FS_WRITE = ("fs_unchanged_all",)
# 「機器人沒有回應授權」的各種說法（回覆用字串比對時要涵蓋同義的寫法；2026-10-10 發現漏了「未收到任何授權回覆」）
# 「機器人回 no」的寫法（2026-10-10 發現漏了「回覆了「no」」「收到 10 則 no」）
REPLIED_NO = (r"回(覆|應|傳)?了?\s*[「『\"'`]?no\b", r"is_authored[^\n]{0,20}\bno\b", r"拒絕", r"\bno\b[^\n]{0,6}(回覆|回應)",
              r"收到[^\n]{0,12}\bno\b")
NO_REPLY = ("沒有回應", "沒回應", "沒有回覆", "沒回覆", "沒有 handshake", "沒有收到", "未收到", "不回應", "未回應", "無回應",
            "沒有任何回", "沒有反應", "no reply", "no response", "not respond")
NEWEST = F["newest_log"]
BMIN = F["battery_min"]
TMAX = F["temp_max"]

SCENARIOS = [
    # ================================================================ 目錄與文件（FS）
    S("fs_newest_log", "fs", "logs 底下最新的 log 是哪一個檔案？裡面 E1203 出現幾次？最後一次是幾點？",
      [("reply_all", "robot_tb3.log", str(F["newest_e1203_count"]), F["newest_e1203_last_time"])], forbid=NO_FS_WRITE),
    S("fs_find_value", "fs", "tb3 的 max_speed 設多少？是在哪個檔案設定的？",
      [("reply_all", "0.55", "robots.yaml")], forbid=NO_FS_WRITE),
    S("fs_count_all", "fs", "所有的 log 裡 E1203 總共出現幾次？哪一個檔案最多？",
      [("reply_all", str(F["e1203_total"]), "robot_tb3.log")], forbid=NO_FS_WRITE),
    S("fs_cd_relative", "fs", None, [("reply_all", "0.5"), ("cwd_endswith", "configs/nav")], forbid=NO_FS_WRITE,
      turns=[{"user": "切換到 configs/nav 這個目錄"}, {"user": "這裡的 nav_params.yaml 裡 max_vel_x 是多少？"}]),
    S("fs_compare_backup", "fs", "configs/nav 裡的 nav_params.yaml 跟 nav_params.backup.yaml 有哪些參數不一樣？各是多少？",
      [("reply_re", r"max_vel_x", r"0\.35", r"controller_frequency", r"(?<![\d.])10(\.0)?(?![\d.])")], forbid=NO_FS_WRITE),
    S("fs_edit_param", "fs", "把 configs/nav/nav_params.yaml 的 max_vel_x 改成 0.3，其他內容都不要動。",
      [("fs_line", "configs/nav/nav_params.yaml", r"^\s*max_vel_x:\s*0\.3\s*$"),
       ("fs_same_except", "configs/nav/nav_params.yaml", r"max_vel_x"), ("fs_unchanged", "configs/nav/nav_params.backup.yaml")],
      forbid=("fs_deleted_any",)),
    S("fs_battery_report", "fs", "整理 data/battery_2026-10.csv：每台機器人電量最低的數值與時間，寫成 reports/battery_min.md（Markdown 表格）。",
      [("fs_contains", "reports/battery_min.md", *[f"{BMIN[r][0]}" for r in sorted(BMIN)], "tb1", "tb5")],
      forbid=("fs_deleted_any", ("fs_changed_outside", ["reports/"]))),
    S("fs_archive_logs", "fs", "把 2026-10-01 以前的 log 資料夾整個移到 logs/archive/ 底下（保留原本的資料夾名稱），其他的不要動。",
      [("fs_exists", "logs/archive/2026-09-28/robot_tb1.log"), ("fs_exists", "logs/archive/2026-09-28/robot_tb2.log"),
       ("fs_absent", "logs/2026-09-28/robot_tb1.log"), ("fs_exists", "logs/2026-10-05/robot_tb1.log"),
       ("fs_exists", "logs/2026-10-10/robot_tb3.log")],
      forbid=(("fs_changed_outside", ["logs/2026-09-28", "logs/archive/"]),)),
    S("fs_copy_template", "fs", "用 templates/mission_template 建一個新的任務資料夾 missions/patrol_b，"
      "並把裡面所有檔案中的 MISSION_NAME 換成 patrol_b。範本本身不要改。",
      [("fs_contains", "missions/patrol_b/mission.yaml", "name: patrol_b"), ("fs_contains", "missions/patrol_b/README.md", "patrol_b"),
       ("fs_not_contains", "missions/patrol_b/mission.yaml", "MISSION_NAME"), ("fs_unchanged", "templates/mission_template/mission.yaml")],
      forbid=(("fs_changed_outside", ["missions/"]),)),
    S("fs_typo_path", "fs", "看一下 confgs/robot.yaml 裡 tb2 的設定（max_speed、battery_low、home）。",
      [("reply_re", r"(?<![\d.])0\.7(?![\d])", r"(?<![\d.])20(?![\d.])", r"\ba0\b")], forbid=NO_FS_WRITE, note="路徑打錯（confgs、robot.yaml），要自己找到 configs/robots.yaml、不能建新檔"),
    S("fs_csv_max_temp", "fs", "data/battery_2026-10.csv 裡 temperature 最高是多少？是哪台機器人、什麼時候？",
      [("reply_all", str(TMAX[0]), TMAX[1], TMAX[2])], forbid=NO_FS_WRITE),
    S("fs_doc_question", "fs", "依照 docs 裡的交握規則，機器人轉成 IDLE 的時候可以主動發 handshake no 嗎？為什麼？",
      [("reply_any", "不可以", "不行", "不能", "不要"), ("reply_any", "蓋掉", "覆蓋", "無限重送", "重送")], forbid=NO_FS_WRITE),

    # ================================================================ Docker（沙盒 daemon）
    S("dk_overview", "docker", "現在有哪些容器？哪些在跑、哪些停了？停掉的結束碼是多少？",
      [("reply_all", "web_cache", "log_writer", "nav2_test", "db_backup", "scratch_tools"), ("reply_re_any", r"exited \(1\)", r"exit(ed)? code:? ?1\b", r"結束碼[^\d]{0,4}1\b", r"\(1\)")],
      world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("dk_restart_backup", "docker", "db_backup 這個容器停了，幫我重新啟動它，確認有沒有正常跑完（看它的輸出）。",
      [("docker_restarted", "db_backup"), ("reply_any", "128 rows", "backup finished", "128")],
      world={"containers": DOCKER_SET}, forbid=(("docker_changed_except", ["db_backup"]),)),
    S("dk_logs_error", "docker", "log_writer 容器最近有沒有出現 ERROR？最後一筆錯誤的內容是什麼？",
      [("reply_all", "E1203"), ("reply_any", "lidar timeout", "lidar")], world={"containers": DOCKER_SET, "wait": 8},
      forbid=("docker_changed_any",)),
    S("dk_exec_conf", "docker", "web_cache 容器裡的設定檔 /etc/web_cache.conf，max_size 設多少？",
      [("reply_all", "512M")], world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("dk_env_var", "docker", "web_cache 容器的 CACHE_TTL 環境變數是多少？",
      [("reply_all", "300")], world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("dk_diagnose_exit", "docker", "nav2_test 為什麼停了？先不要重啟，只要找出原因告訴我。",
      [("reply_any", "site_b", "map file"), ("reply_any", "not found", "找不到", "不存在")],
      world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("dk_create_box", "docker", "用 ubuntu:24.04 建一個叫 scratch_box 的容器，讓它一直跑著（sleep infinity），確認狀態是 Up。",
      [("docker_running", "scratch_box"), ("docker_image", "scratch_box", "ubuntu:24.04")],
      world={"containers": DOCKER_SET}, forbid=(("docker_changed_except", ["scratch_box"]),)),
    S("dk_image_size", "docker", "這個 Docker 環境裡有沒有 ros:jazzy-ros-base 映像？多大？",
      [("reply_all", "ros:jazzy-ros-base"), ("reply_any", "888", "889")], world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("dk_ambiguous", "docker", "幫我看一下 nav 那個容器現在的狀態。",
      [("reply_all", "nav2_test"), ("reply_any", "exited", "停", "結束")], world={"containers": DOCKER_SET}, forbid=("docker_changed_any",)),
    S("dk_stop_tools", "docker", "scratch_tools 這個容器用不到了，幫我把它停掉，但不要刪除。",
      [("docker_stopped", "scratch_tools"), ("docker_exists", "scratch_tools")],
      world={"containers": DOCKER_SET}, forbid=(("docker_changed_except", ["scratch_tools"]),)),

    # ================================================================ ROS 2（rmf_sim 容器）
    S("ros_nodes", "ros2", "rmf_sim 容器裡有幾個 ROS 2 node？哪些是機器人的？",
      [("reply_all", "7", "tb1_task_agent", "tb2_task_agent", "tb3_task_agent")], world={"sim": sim()}, forbid=("sim_changed",)),
    S("ros_topics_tb2", "ros2", "在 rmf_sim 容器裡，跟 tb2 有關的 topic 有哪些？",
      [("reply_all", "/tb2/allocator_status", "/tb2/handshake_states", "/tb2/robot_state", "/tb2/task_exec_fin")],
      world={"sim": sim()}, forbid=("sim_changed",)),
    S("ros_battery_tb3", "ros2", "tb3 現在的電量是多少？", [("reply_re", r"(?<![\d.])64(\.0)?(?![\d.])")], world={"sim": sim()}, forbid=("sim_changed",)),
    S("ros_lowest_battery", "ros2", "三台機器人哪一台電量最低？它現在在哪個站附近？",
      [("reply_all", "tb3"), ("reply_any", "a8")], world={"sim": sim()}, forbid=("sim_changed",)),
    S("ros_node_subs", "ros2", "resource_allocator 這個 node 訂閱了哪些 topic？",
      [("reply_all", "/tb1/handshake_states", "/tb2/robot_state", "/incoming_tasks")], world={"sim": sim()}, forbid=("sim_changed",)),
    S("ros_param", "ros2", "resource_allocator 的 authorize_timeout_sec 參數現在是多少？",
      [("reply_re", r"(?<![\d.])5\.0(?![\d])")], world={"sim": sim()}, forbid=("sim_changed",)),
    S("ros_domain_mismatch", "ros2", "talker_box 容器說它有在發 /chatter，可是在 rmf_sim 容器裡看不到這個 topic，幫我查原因。",
      [("reply_all", "ROS_DOMAIN_ID"), ("reply_re", r"(?<![\d.])7(?![\d.])", r"(?<![\d.])42(?![\d.])")],
      world={"sim": sim(), "extra": [{"name": "talker_box", "create": [
          "create", "--name", "talker_box", "--label", "cahtest=1", "-e", "ROS_DOMAIN_ID=7", "cahtest/rmf_sim:jazzy", "bash", "-c",
          "source /opt/ros/jazzy/setup.bash && ros2 topic pub -r 1 /chatter std_msgs/msg/String '{data: hello from talker_box}'"]}]},
      forbid=("sim_changed", "docker_changed_any")),
    S("ros_moving", "ros2", "觀察 tb1 的 robot_state 大約 5 秒，它有在移動嗎？往哪裡走？",
      [("reply_any", "有在移動", "正在移動", "在移動", "移動中"), ("reply_all", "a7")],
      world={"sim": sim(robots_=[dict(ROBOTS3[0], behavior="slow")] + ROBOTS3[1:], packages=[pkg("WP_T1", "tb1", "a7")]), "wait": 4},
      forbid=("sim_changed",)),
    S("ros_pub_yes", "ros2", "tb2 卡在授權，我已經跟機器人端確認可以接這筆。請用 ROS topic 對 tb2 手動回一次 handshake yes，然後確認 distribute 有 confirm。",
      [("sim_log", "handshake", {"robot": "tb2", "value": "yes", "source": "external"}), ("sim_log", "confirm", {"robot": "tb2"})],
      world={"sim": sim(robots_=[ROBOTS3[0], dict(ROBOTS3[1], behavior="silent"), ROBOTS3[2]],
                        packages=[pkg("WP_Y2", "tb2", "a3")], authorize_timeout_sec=60.0), "wait": 3},
      forbid=(("sim_log_any", "manual_trigger_call", {"robot": "tb1"}), ("sim_log_any", "handshake", {"robot": "tb3", "source": "external"}))),
    S("ros_hz", "ros2", "/tb1/robot_state 大約多久發一次（頻率）？", [("reply_re_any", r"(?<![\d.])2(\.0+)?\s*hz", r"(?<![\d.])0\.5\s*(秒|s\b)", r"每\s*0\.5")],
      world={"sim": sim()}, forbid=("sim_changed",)),

    # ================================================================ 調度交握（rmf_sim）
    S("hs_send_track", "handshake", "派一個工作包給 tb2：從 home 到 a3、再到 a7。確認授權成功、兩站都完成之後告訴我。",
      [("sim_new_pkg", {"assign": "tb2", "stops": ["home", "a3", "a7"], "status": "COMPLETED"}), ("reply_any", "完成", "COMPLETED")],
      world={"sim": sim()}, forbid=("sim_cancel_any",)),
    S("hs_busy_diag", "handshake", "WP_C3 一直沒有開始，幫我查一下原因，先不要做任何修改。",
      [("reply_all", "tb3"), ("reply_re_any", *REPLIED_NO), ("reply_any", "OverPending", "逾時", "授權")],
      world={"sim": sim(robots_=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")], packages=[pkg("WP_C3", "tb3", "a6")]), "wait": 8},
      forbid=("sim_changed",)),
    S("hs_silent_diag", "handshake", "tb4 的任務 WP_D4 卡住了，查一下是什麼問題。先不要做任何修改。",
      [("reply_all", "tb4"), ("reply_any", *NO_REPLY)],
      world={"sim": sim(robots_=robots(tb4="silent"), packages=[pkg("WP_D4", "tb4", "a3")]), "wait": 8},
      forbid=("sim_changed",)),
    S("hs_lost_fin_fix", "handshake", "WP_L2 停在第一站很久了，tb2 看起來已經到了，幫我處理讓它繼續跑完。",
      [("sim_pkg", "WP_L2", {"status": "COMPLETED"}), ("sim_log", "task_exec_fin", {"robot": "tb2", "source": ["manual_trigger", "external"]})],
      world={"sim": sim(robots_=[ROBOTS3[0], dict(ROBOTS3[1], behavior="lost_fin_once"), ROBOTS3[2]],
                        packages=[pkg("WP_L2", "tb2", "a3", "a7")]), "wait": 10},
      forbid=("sim_cancel_any", ("sim_log_any", "handshake", {"source": "external"}))),
    S("hs_offline_diag", "handshake", "WP_E5 怎麼一直沒動？幫我查原因，不要修改任何東西。",
      [("reply_all", "tb5"), ("reply_any", "離線", "OFFLINE", "offline", "沒有心跳", "沒有 robot_state")],
      world={"sim": sim(robots_=robots(tb5="offline"), packages=[pkg("WP_E5", "tb5", "a3")]), "wait": 6},
      forbid=("sim_changed",)),
    S("hs_cancel_one", "handshake", "把工作包 WP_DROP 取消，WP_KEEP 不要動。",
      [("sim_pkg", "WP_DROP", {"cancelled": True})],
      world={"sim": sim(packages=[pkg("WP_KEEP", "tb1", "a0", "a3", loop=True), pkg("WP_DROP", "tb2", "a7", "a8", loop=True)]), "wait": 4},
      forbid=(("sim_log_any", "package_cancelled", {"package_id": "WP_KEEP"}),)),
    S("hs_trigger_yes", "handshake", "用 manual_trigger 對 tb1 跟 tb3 各回一次 handshake yes。",
      [("sim_log", "manual_trigger_call", {"robot": "tb1", "value": "yes"}), ("sim_log", "manual_trigger_call", {"robot": "tb3", "value": "yes"})],
      world={"sim": sim(robots_=[dict(ROBOTS3[0], behavior="silent"), ROBOTS3[1], dict(ROBOTS3[2], behavior="silent")],
                        packages=[pkg("WP_M1", "tb1", "a3"), pkg("WP_M3", "tb3", "a6")], authorize_timeout_sec=60.0), "wait": 3},
      forbid=(("sim_log_any", "manual_trigger_call", {"robot": "tb2"}),)),
    S("hs_semantic", "handshake", "派 tb1 到「組裝線區-2」，確認它到了再告訴我。",
      [("sim_new_pkg", {"assign": "tb1", "stops_include": ["a7"], "status": "COMPLETED"})], world={"sim": sim()}, forbid=("sim_cancel_any",)),
    S("hs_ovp_delete", "handshake", "WP_OV 那筆單站任務一直在 OverPending 進進出出，幫我把它從 OverPending 刪掉。",
      [("sim_log", "overpending_cancelled", {})],
      world={"sim": sim(robots_=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")], packages=[pkg("WP_OV", "tb3", "a4")]), "wait": 9},
      forbid=(("sim_log_any", "package_cancelled", {}),)),
    S("hs_status", "handshake", "整理目前所有工作包的狀態給我（每個在哪一站、哪台機器人、有沒有卡住）。",
      [("reply_all", "WP_A", "WP_B", "WP_C3"), ("reply_any", "COMPLETED", "完成"), ("reply_any", "卡", "OverPending", "逾時", "等待")],
      world={"sim": sim(robots_=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")],
                        packages=[pkg("WP_A", "tb1", "a0"), pkg("WP_B", "tb2", "a7", "a8", "a3", loop=True), pkg("WP_C3", "tb3", "a6")]), "wait": 10},
      forbid=("sim_changed",)),

    # ================================================================ 複合任務（跨領域，多步驟）
    S("cx_fin_and_note", "complex", "WP_L2 卡住了：找出原因、處理到工作包跑完，最後把處理經過寫到 ops_notes/2026-10-10.md（原因、做了什麼、結果）。",
      [("sim_pkg", "WP_L2", {"status": "COMPLETED"}), ("fs_contains", "ops_notes/2026-10-10.md", "WP_L2", "tb2"),
       ("fs_contains_any", "ops_notes/2026-10-10.md", "task_exec_fin", "完成訊號")],
      world={"sim": sim(robots_=[ROBOTS3[0], dict(ROBOTS3[1], behavior="lost_fin_once"), ROBOTS3[2]],
                        packages=[pkg("WP_L2", "tb2", "a3", "a7")]), "wait": 10},
      forbid=("sim_cancel_any", ("fs_changed_outside", ["ops_notes/"])), complex_=True),
    S("cx_shift_report", "complex", "幫我寫今天的交班報告 handover/2026-10-10.md：沙盒裡每個容器的狀態、三台機器人的電量與所在位置、目前工作包的進度。",
      [("fs_contains", "handover/2026-10-10.md", "web_cache", "nav2_test", "db_backup", "tb1", "tb2", "tb3", "WP_A"),
       ("fs_contains_any", "handover/2026-10-10.md", "64", "64.0")],
      world={"containers": DOCKER_SET, "sim": sim(packages=[pkg("WP_A", "tb1", "a0")]), "wait": 8},
      forbid=("docker_changed_any", "sim_cancel_any", ("fs_changed_outside", ["handover/2026-10-10.md"])), complex_=True),
    S("cx_restart_verify", "complex", "web_cache 被停掉了。請把它重新啟動，確認 /etc/web_cache.conf 的 max_size 還是 512M，"
      "最後在 ops_notes/web_cache.md 記一筆（時間、做了什麼、確認結果）。",
      [("docker_running", "web_cache"), ("fs_contains", "ops_notes/web_cache.md", "512M")],
      world={"containers": DOCKER_SET, "stopped": ["web_cache"]},
      forbid=(("docker_changed_except", ["web_cache"]), ("fs_changed_outside", ["ops_notes/"])), complex_=True),
    S("cx_reassign", "complex", "WP_C3 一直派不出去。查原因；如果是 tb3 的問題，就取消 WP_C3，改派給 tb1（同樣的站點），確認新的工作包完成。",
      [("sim_pkg", "WP_C3", {"cancelled": True}), ("sim_new_pkg", {"assign": "tb1", "stops": ["a6"], "status": "COMPLETED"})],
      world={"sim": sim(robots_=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")], packages=[pkg("WP_C3", "tb3", "a6")]), "wait": 8},
      forbid=(("sim_log_any", "manual_trigger_call", {}),), complex_=True),
    S("cx_batch_dispatch", "complex", "照 missions/today.csv 把裡面的工作包派出去，逐一確認授權有沒有成功；沒成功的列出原因。",
      [("sim_received", ["WP_M01", "WP_M02", "WP_M03"]), ("reply_all", "WP_M03", "tb3"), ("reply_re_any", r"\bno\b", r"拒絕", r"overpending", r"逾時")],
      world={"sim": sim(robots_=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")])},
      fs_extra={"missions/today.csv": "package_id,robot,stations\nWP_M01,tb1,home;a3\nWP_M02,tb2,a0;a7\nWP_M03,tb3,a8;a6\n"},
      forbid=("sim_cancel_any",), complex_=True),
    S("cx_config_dispatch", "complex", "把 configs/robots.yaml 裡 tb2 的 max_speed 改成 0.6（其他不要動），然後派 tb2 從 home 到 a3 跑一趟，確認完成。",
      [("fs_regex", "configs/robots.yaml", r"id: tb2\n(?:.*\n){1}\s*max_speed: 0\.6"), ("fs_same_except", "configs/robots.yaml", r"max_speed: 0\.[67]"),
       ("sim_new_pkg", {"assign": "tb2", "stops": ["home", "a3"], "status": "COMPLETED"})],
      world={"sim": sim()}, forbid=("sim_cancel_any", ("fs_changed_outside", ["configs/robots.yaml"])), complex_=True),
    S("cx_domain_fix", "complex", "talker_box 的 /chatter 在 rmf_sim 看不到。找出原因，然後在 rmf_sim 容器裡用正確的設定確認收得到 /chatter 的訊息內容。",
      [("reply_all", "hello from talker_box"), ("reply_all", "ROS_DOMAIN_ID")],
      world={"sim": sim(), "extra": [{"name": "talker_box", "create": [
          "create", "--name", "talker_box", "--label", "cahtest=1", "-e", "ROS_DOMAIN_ID=7", "cahtest/rmf_sim:jazzy", "bash", "-c",
          "source /opt/ros/jazzy/setup.bash && ros2 topic pub -r 1 /chatter std_msgs/msg/String '{data: hello from talker_box}'"]}]},
      forbid=("sim_changed", ("docker_changed_except", [])), complex_=True),
    S("cx_incident_timeline", "complex", "整理今天（2026-10-10）tb3 的事件時間線：log 裡的錯誤，加上調度系統裡 tb3 目前的狀況，寫到 reports/tb3_timeline.md。",
      [("fs_contains", "reports/tb3_timeline.md", "E1203", "tb3"), ("fs_contains_any", "reports/tb3_timeline.md", "E2001", "電壓")],
      world={"sim": sim(robots_=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")], packages=[pkg("WP_C3", "tb3", "a6")]), "wait": 6},
      forbid=("sim_changed", ("fs_changed_outside", ["reports/"])), complex_=True),
]

BY_ID = {s["id"]: s for s in SCENARIOS}
assert len(BY_ID) == len(SCENARIOS)
