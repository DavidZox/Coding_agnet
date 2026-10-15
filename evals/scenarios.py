"""評測情境與假工具輸出（fixture）。

每個情境：
- id／desc：名稱與要測的行為。
- turns：依序送出的使用者訊息，每一句附 expect（這一句的回合結束後要成立的條件，見 worker.evaluate）。
- state：開始前的 agent 狀態（target_container…）；memory：取代 Memory.md 的內容（None＝用專案原本的）。
- seeds：預先放進 logs/tool_results/ 的「之前的存檔」（模擬上次啟動查過的東西），連同 index.md 與檢索清單的一行。
- fixtures：這個情境專用的假工具輸出（覆寫 COMMON_FIXTURES 的同名腳本）。
- guard：執行前關卡出現時怎麼回答（approve／deny）。

外部世界（docker、ROS2、調度系統）一律用假資料，結果才可重現；存檔工具（result_*）、modify_memory 與本機檔案類
技能（ls、cat、grep、find、cd）在臨時的專案副本裡真的執行。假資料故意做得夠大（fleet_states 約 1 萬 2 千字元），
讓 harness 模式一定走獨立 session 擷取、claude_code 模式一定被截成頭尾——要問的那幾台車放在中間。"""
import re

# ---------------------------------------------------------------- 假資料
ROBOTS = [  # name, battery, x, y, mode
    ("tb1", 81.2, 3.41, 7.02, "MOVING"), ("tb2", 77.9, 5.10, 1.33, "IDLE"), ("tb3", 69.4, 8.76, 2.05, "MOVING"),
    ("tb4", 58.0, 0.92, 9.48, "CHARGING"), ("tb5", 44.7, 6.60, 6.61, "IDLE"), ("tb6", 63.5, 10.25, 4.18, "MOVING"),
    ("tb7", 52.3, 12.4, -3.7, "WAITING"), ("tb8", 90.1, 2.22, -1.05, "IDLE"), ("tb9", 15.0, 7.77, -6.3, "MOVING"),
    ("tb10", 88.8, 1.11, 3.33, "IDLE"), ("tb11", 72.6, 9.90, 8.80, "MOVING"), ("tb12", 66.0, 4.44, -2.22, "IDLE"),
]


def fleet_states_output():
    lines = ["[PASS] '/fleet_states_json' 的一筆訊息:", "name: tinyRobot", "robots:"]
    for i, (name, batt, x, y, mode) in enumerate(ROBOTS):
        lines += [
            f"- name: {name}", "  model: tinyRobot", f"  task_id: 'WP{100 + i:03d}-{i % 3}'", f"  seq: {18230 + i * 7}",
            "  mode:", f"    mode: {mode}", "    mode_request_id: 0", f"  battery_percent: {batt}",
            "  location:", f"    t: {{sec: 1759000{100 + i}, nanosec: {45000000 + i}}}", f"    x: {x}", f"    y: {y}",
            f"    yaw: {round(0.31 * i, 2)}", "    level_name: L1", f"    index: {i * 3}", "  path:",
        ]
        for k in range(6):
            lines.append(f"  - {{x: {round(x + 0.5 * k, 2)}, y: {round(y - 0.25 * k, 2)}, yaw: {round(0.1 * k, 2)}, "
                         f"level_name: L1, index: {i * 10 + k}, obey_approach_speed_limit: false}}")
    lines += ["---", "[TARGET_CONTAINER] rmf_sim"]
    return "\n".join(lines)


TOPICS = ["/fleet_states_json", "/incoming_tasks", "/incoming_work_packages", "/task_summaries", "/dispatch_states",
          "/building_map", "/map", "/costmap", "/cmd_vel", "/odom", "/tf", "/tf_static", "/scan", "/battery_state",
          "/door_states", "/lift_states", "/robot_state", "/robot_path_requests", "/robot_mode_requests",
          "/parameter_events", "/rosout", "/orchestrtor/status", "/distribute/overpending"]


def containers_table(nav2_status="Exited (0) 2 days ago"):
    rows = [("rmf_sim", "Up 3 hours", "rmf:humble", "a1b2c3d4e5f6"), ("ros2_humble", "Up 3 hours", "osrf/ros:humble", "0f9e8d7c6b5a"),
            ("nav2_test", nav2_status, "nav2:dev", "1234abcd5678"), ("db_cache", "Up 5 days", "redis:7", "99aa88bb77cc")]
    running = sum(1 for r in rows if r[1].startswith("Up"))
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(("NAME", "STATUS", "IMAGE", "CONTAINER ID"))]
    fmt = lambda cols: "  ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip()
    table = "\n".join([fmt(("NAME", "STATUS", "IMAGE", "CONTAINER ID"))] + [fmt(r) for r in rows])
    return f"[PASS] 容器（含已停止）：共 {len(rows)} 個，運行中 {running} 個\n{table}"


def _has(args, word):
    return any(word in str(a) for a in args)


_ECHO_USAGE = "用法: scripts/ROS2_topic_echo_cmd.py [container_name] <topic_name> [timeout_seconds] [--duration 秒] [--where 條件]"


def _topic_echo(args, agent):
    """比照真實腳本：不認識的選項、--where 沒有 --duration 都回 [ERROR]；--duration 回「統計＋原始訊息」的格式。"""
    bad = [a for a in args if str(a).startswith("--") and a not in ("--duration", "--where")]
    if bad:
        return (f"[ERROR] 不認識的選項 {bad[0]!r}：位置參數依序是 [container_name] <topic_name> [timeout_seconds]，"
                f"選項只有 --duration 與 --where。\n{_ECHO_USAGE}")
    if "--where" in args and "--duration" not in args:
        return f"[ERROR] --where 只能與 --duration 一起用（要有一段時間的訊息才有得判斷）。\n{_ECHO_USAGE}"
    if _has(args, "fleet_states"):
        if "--duration" in args:
            i = args.index("--duration")
            secs = args[i + 1] if i + 1 < len(args) else "5"
            where = args[args.index("--where") + 1] if "--where" in args and args.index("--where") + 1 < len(args) else ""
            body = fleet_states_output().split("\n", 1)[1].rsplit("\n---\n", 1)[0]
            lines = [f"[PASS] 觀察 '/fleet_states_json' {secs} 秒：收到 1 則訊息（約 {1 / max(float(secs), 1):.2f} Hz）",
                     "欄位變化（1 則、2 個欄位）：", "- 所有欄位在觀察期間都沒有變化", "固定不變：name=tinyRobot；robots=[12 項]"]
            if where:
                field = re.split(r"\s*(?:<=|>=|==|!=|<|>)\s*", where)[0]
                lines.append(f"條件 {where}：找不到欄位「{field}」（可用欄位：name, robots）")
            return "\n".join(lines + ["原始訊息（共 1 則，依接收順序）：", "--- #1", body, "[TARGET_CONTAINER] rmf_sim"])
        return fleet_states_output()
    if _has(args, "incoming_tasks"):
        return ("[PASS] '/incoming_tasks' 的一筆訊息:\ntask_id: WP107-1\nrequester: web_console\ncategory: regular\n"
                "priority: normal\n---\n[TARGET_CONTAINER] rmf_sim")
    return ("[ERROR] 讀取 topic 失敗：找不到指定的 topic 或目前沒有任何 publisher（請先用 ROS2_topic_list 確認名稱）")


def _topic_list(args, agent):
    items = TOPICS
    if "--filter" in args:
        i = args.index("--filter")
        kws = [k.lower() for k in args[i + 1:i + 2]]
        hits = [t for t in items if any(k in t.lower() for k in kws)]
        return (f"[PASS] 容器 'rmf_sim' 的 topic：共 {len(items)} 個，其中含「{'／'.join(args[i + 1:i + 2])}」的 {len(hits)} 個：\n"
                + "\n".join(hits) + "\n[TARGET_CONTAINER] rmf_sim")
    return f"[PASS] 容器 'rmf_sim' 的 topic：共 {len(items)} 個：\n" + "\n".join(items) + "\n[TARGET_CONTAINER] rmf_sim"


NODES = ["/orchestrtor", "/task_agent", "/distribute", "/fleet_adapter_tinyRobot", "/costmap_server", "/map_server",
         "/web_console_bridge", "/door_supervisor", "/lift_supervisor"]


def _node_list(args, agent):
    return f"[PASS] 容器 'rmf_sim' 的 node：共 {len(NODES)} 個：\n" + "\n".join(NODES) + "\n[TARGET_CONTAINER] rmf_sim"


def _node_info(args, agent):
    if _has(args, "task_agent"):
        return ("[PASS] 節點 /task_agent 的資訊（ros2 node info）:\n/task_agent\n  Subscribers:\n"
                "    /incoming_tasks: rmf_task_msgs/msg/ApiRequest\n    /fleet_states_json: std_msgs/msg/String\n"
                "  Publishers:\n    /task_summaries: rmf_task_msgs/msg/TaskSummary\n    /rosout: rcl_interfaces/msg/Log\n"
                "  Service Servers:\n    /task_agent/get_parameters: rcl_interfaces/srv/GetParameters\n[TARGET_CONTAINER] rmf_sim")
    return "[ERROR] 找不到指定的 ROS2 節點（請先用 ROS2_node_list 確認名稱，需含命名空間前綴，例如 /nav_node）"


def _docker_open(args, agent):
    name = (args[0] if args else "").strip()
    for real in ("rmf_sim", "ros2_humble", "db_cache"):
        if name and name in real:
            return (f"[PASS] 已成功連線至 '{real}'，並設為目前的目標容器（之後 docker_runcmd／ROS2_* 可省略容器名稱；要換容器再用一次 docker_open）。\n"
                    f"連線成功\n/root\nroot\n[TARGET_CONTAINER] {real}")
    return f"[ERROR] 找不到容器 '{name}'（名稱錯誤或尚未建立；請先用 docker_containers 查看現有容器的完整名稱）"


def _docker_runcmd(args, agent):
    """比照真實腳本（skills_system/scripts/docker_runcmd_cmd.py）：參數怎麼解析、docker CLI 的提示、找不到容器的錯誤。"""
    import sys as _sys
    _dir = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))),
                                      "skills_system", "scripts")
    if _dir not in _sys.path:
        _sys.path.insert(0, _dir)
    from docker_runcmd_cmd import docker_cli_misuse
    joined = " ".join(str(a) for a in args if a != "--timeout")
    for cand in (joined, " ".join(str(a) for a in args[1:])):
        hint = docker_cli_misuse(cand)
        if hint:
            return f"[ERROR] {hint}"
    positional, i = [], 0
    while i < len(args):
        if args[i] == "--timeout":
            i += 2
            continue
        positional.append(args[i])
        i += 1
    # 比照真實腳本：第一個參數是現有容器名稱才當容器，其餘接起來是指令；否則整串都是指令（模型常忘記引號）
    if len(positional) >= 2 and positional[0] in ("rmf_sim", "ros2_humble", "db_cache", "nav2_test", "rmf"):
        container, command = positional[0], " ".join(positional[1:])
    else:
        container, command = (agent.target_container or ""), " ".join(positional)
    if container not in ("rmf_sim", "ros2_humble", "db_cache"):
        return (f"[ERROR] 在容器 '{container}' 內執行指令 失敗（exit code 1）: 找不到容器 '{container}'（名稱錯誤或尚未建立；"
                f"請先用 docker_containers 查看現有容器的完整名稱）")
    if "/opt/ros" in command and command.strip().startswith(("ls", "cd")):
        out = "humble"
    elif "ls" in command:
        out = "bin\netc\nopt\nroot\nws"
    else:
        out = "（沒有輸出）"
    marker = f"\n[TARGET_CONTAINER] {container}" if container != agent.target_container else ""
    return f"[PASS] 容器 '{container}' 內 `{command}` 執行完成:\n{out}\n/root{marker}"


COMMON_FIXTURES = {
    "docker_containers_cmd.py": lambda args, agent: containers_table(),
    "docker_open_cmd.py": _docker_open,
    "docker_runcmd_cmd.py": _docker_runcmd,
    "ROS2_topic_echo_cmd.py": _topic_echo,
    "ROS2_topic_list_cmd.py": _topic_list,
    "ROS2_node_list_cmd.py": _node_list,
    "ROS2_node_info_cmd.py": _node_info,
    "workpackage_send_cmd.py": lambda args, agent: (
        f"[PASS] work package「{args[0] if args else 'auto'}」已送出：站點 {args[1] if len(args) > 1 else '?'}，循環：不循環（只跑一輪），"
        f"機器人：{args[args.index('--amr') + 1] if '--amr' in args and args.index('--amr') + 1 < len(args) else '交給 distribute 挑'}"),
    "workpackage_status_cmd.py": lambda args, agent: "[PASS] 目前沒有執行中的 work package。",
}
# 在臨時副本裡真的執行的腳本（不碰外部世界）
REAL_SCRIPTS = {"result_grep_cmd.py", "result_view_cmd.py", "result_list_cmd.py", "modify_memory_cmd.py",
                "ls_cmd.py", "cat_cmd.py", "grep_cmd.py", "find_file_cmd.py", "cd_cmd.py", "code_ast_reader_cmd.py"}

# ---------------------------------------------------------------- 預先放好的舊存檔（模擬上次啟動查過的東西）
NODE_LIST_YESTERDAY = {
    "id": 501, "session": "20260926_101500", "ts": "2026-09-26 10:15:00", "script": "ROS2_node_list_cmd.py",
    "skill": "ROS2_node_list", "task": "調度系統有哪些 node 在跑",
    "output": f"[PASS] 容器 'rmf_sim' 的 node：共 {len(NODES)} 個：\n" + "\n".join(NODES) + "\n[TARGET_CONTAINER] rmf_sim",
    "hint": "調度系統有哪些 node：rmf_sim 的 node 清單，含 /task_agent、/orchestrtor 等 9 個",
}
CONTAINERS_YESTERDAY = {
    "id": 502, "session": "20260926_101500", "ts": "2026-09-26 10:20:00", "script": "docker_containers_cmd.py",
    "skill": "docker_containers", "task": "有哪些容器在跑", "output": containers_table(nav2_status="Up 20 hours"),
    "hint": "有哪些容器在跑：容器清單，rmf_sim、ros2_humble、nav2_test、db_cache 都在運行",
}
_TOPICS_AM = [t for t in TOPICS if t != "/distribute/overpending"] + ["/old_debug"]
_TOPICS_PM = TOPICS + ["/emergency_stop"]
TOPICS_MORNING = {
    "id": 503, "session": "20260926_101500", "ts": "2026-09-26 10:30:00", "script": "ROS2_topic_list_cmd.py",
    "skill": "ROS2_topic_list", "task": "早上看一下 rmf_sim 有哪些 topic",
    "output": f"[PASS] 容器 'rmf_sim' 的 topic：共 {len(_TOPICS_AM)} 個：\n" + "\n".join(_TOPICS_AM),
    "hint": "早上 rmf_sim 有哪些 topic：topic 清單，共 23 個",
}
TOPICS_AFTERNOON = {
    "id": 504, "session": "20260926_150000", "ts": "2026-09-26 15:05:00", "script": "ROS2_topic_list_cmd.py",
    "skill": "ROS2_topic_list", "task": "下午再看一次 rmf_sim 的 topic",
    "output": f"[PASS] 容器 'rmf_sim' 的 topic：共 {len(_TOPICS_PM)} 個：\n" + "\n".join(_TOPICS_PM),
    "hint": "下午再看 rmf_sim 的 topic：topic 清單，共 24 個",
}

STALE_MEMORY = """# Long Term Memory

[05-21 16:57] 操作流程規範 | 多步驟任務 | 嚴格依使用者指定的順序執行，一次推論只輸出一個指令，每一步等系統回傳結果後再進行下一步

[09-24 21:31] 診斷經驗 | 任務流程驗證 | 確認了所有核心 Topic (Costmap, Orchestrator, Cmd_vel) 均活躍，系統整體健康。
"""

# ---------------------------------------------------------------- 📊 數據解析的假資料（容器內的數據技能不真的執行）
DATA_PATH = "/workspace/data/exp_20261014_084506"
ROSOUT_DIGEST = """[PASS] Log 智慧過濾：31 則 Log → 9 個唯一訊號；層級：INFO 7、WARN 2
來源：bag 的 /rosout（時間＝MCAP log_time，與其他 Topic 同一個時鐘）
數據：exp_20261014_084506（1791967507.011 ～ 1791967558.900，51.9 秒）；[+秒] 是距離數據開頭的時間
L15  INFO  ×1    1791967507.532[+0.52s]  blackbox_recorder：Configuring BlackboxRecorderNode...
L28  WARN  ×1    1791967507.760[+0.75s]  safety_motion_controller：GATE mode=PROTECTIVE_STOP latched=False reasons=['NO_SAFETY_COMMAND_YET', 'NO_CMD_VEL_RAW'] reaction=''
L29  WARN  ×1    1791967508.236[+1.22s]  safety_motion_controller：GATE mode=PROTECTIVE_STOP latched=False reasons=['MON_INITIALIZING', 'NO_CMD_VEL_RAW'] reaction='INIT'
L30  INFO  ×1    1791967522.547[+15.54s]  safety_motion_controller：GATE mode=NORMAL latched=False reasons=['NO_CMD_VEL_RAW'] reaction='NONE'
（略過錄製工具 rosbag2 自己的 Log 22 個訊號；--all-nodes 顯示）"""
CMD_VEL_FEATURES = """[PASS] 特徵量測：/cmd_vel（geometry_msgs/msg/Twist）｜數據 exp_20261014_084506（1791967507.011 ～ 1791967558.900）
整份數據：1791967507.011 ～ 1791967558.900（51.9 秒）（數據開頭 +0.00s ～ +51.89s）；[+秒] 是距離數據開頭的時間
  訊息 1010 筆，平均 19.901 Hz，最大間隔 0.35 秒
  ▸ linear.x（scalar，數值，double）
     linear.x：min 0  max 0.42  mean 0.1137  std 0.1521  slope 0.0031/s  首 0→末 0（1010 筆）
       最大跳變 0→0.42 @ 1791967530.102[+23.09s]
異常指標（程式判斷）：沒有尖峰、沒有狀態跳轉、沒有訊息中斷"""
ANALYSIS_REPORT = """[PASS] 📊 數據診斷報告（job 20261014_181445：4 個 worker、模型呼叫 18 次、74 秒）
問題：安全閘為什麼一開始是 PROTECTIVE_STOP？什麼時候恢復？
數據：exp_20261014_084506（51.889 秒）；時間窗：W1 +0.00s～+30.54s（L28 WARN safety_motion_controller）
結論：安全閘在 +0.75s 因為還沒收到安全指令與速度輸入而進入 PROTECTIVE_STOP，系統健康監控初始化完成後於 +15.54s 恢復 NORMAL。
根因（信心 medium）：L28／L29 記錄 NO_SAFETY_COMMAND_YET、MON_INITIALIZING；/system/safety_command 的 primary_reaction 在 +15.53s 由 INIT 變成 NONE，緊接著 +15.54s 安全閘 mode 變成 NORMAL。
時間線：
- +0.75s｜L28｜進入 PROTECTIVE_STOP（NO_SAFETY_COMMAND_YET、NO_CMD_VEL_RAW）
- +15.53s｜/system/safety_command｜primary_reaction INIT → NONE
- +15.54s｜/system/safety_gate_status｜mode PROTECTIVE_STOP → NORMAL
尚未確認：/cmd_vel_raw 不在數據裡，NO_CMD_VEL_RAW 無法由數據證實。
建議：下次錄製加上 /cmd_vel_raw。
各 worker：W1 /system/safety_gate_status（⚠️ 有異常）；W2 /system/safety_command（⚠️ 有異常）；W3 /cmd_vel（沒有異常）
完整報告：logs/analysis_jobs/20261014_181445/report.md（各 worker 的局部報告在 workers/）"""

# ---------------------------------------------------------------- 情境
SCENARIOS = [
    {"id": "analysis_route_diagnose", "desc": "問「為什麼、什麼時候恢復」要同時看 Log 與多個 Topic：用 analysis_run（多 agent 數據診斷），依報告回答",
     "state": {"target_container": "ros2_web", "analysis_data": DATA_PATH}, "pseudo": {"analysis_run": ANALYSIS_REPORT},
     "turns": [{"user": "剛剛錄的那份數據裡，安全閘為什麼一開始是 PROTECTIVE_STOP？什麼時候恢復的？幫我找根因",
                "expect": {"tools_any": ["analysis_run"], "reply_any": ["15.5"]}}]},
    {"id": "analysis_route_single_key", "desc": "只問一個 Topic 的一個數值：直接用 mcap_feature_measure，不用派多 agent 的 analysis_run",
     "state": {"target_container": "ros2_web", "analysis_data": DATA_PATH},
     "fixtures": {"mcap_feature_measure_cmd.py": CMD_VEL_FEATURES}, "pseudo": {"analysis_run": ANALYSIS_REPORT},
     "turns": [{"user": "這份數據裡 /cmd_vel 的 linear.x 最大是多少？",
                "expect": {"tools_any": ["mcap_feature_measure"], "tools_none": ["analysis_run"], "reply_any": ["0.42"]}}]},
    {"id": "analysis_route_log", "desc": "問 Log 裡有哪些警告：用 rosout_parser（去重後的唯一訊號），不用派 analysis_run",
     "state": {"target_container": "ros2_web", "analysis_data": DATA_PATH},
     "fixtures": {"rosout_parser_cmd.py": ROSOUT_DIGEST}, "pseudo": {"analysis_run": ANALYSIS_REPORT},
     "turns": [{"user": "這份數據錄製期間有哪些 WARN 等級的 Log？",
                "expect": {"tools_any": ["rosout_parser"], "tools_none": ["analysis_run"], "reply_any": ["PROTECTIVE_STOP"]}}]},
    {"id": "containers_basic", "desc": "小回傳：列容器並回答哪些在跑",
     "turns": [{"user": "目前有哪些容器？哪些正在跑？",
                "expect": {"tools_any": ["docker_containers"], "reply_all": ["rmf_sim", "ros2_humble", "db_cache"],
                           "archive_lookup": False}}]},
    {"id": "fleet_battery", "desc": "大量回傳：在 12 台車的狀態裡找中間那台的電量",
     "state": {"target_container": "rmf_sim"},
     "turns": [{"user": "幫我讀一下 topic /fleet_states_json，tb6 現在電量多少？",
                "expect": {"tools_any": ["ROS2_topic_echo"], "reply_any": ["63.5"]}}]},
    {"id": "fleet_followup", "desc": "追問第一次回答沒寫到的細節（要回存檔，不是亂猜）",
     "state": {"target_container": "rmf_sim"},
     "turns": [{"user": "幫我讀一下 topic /fleet_states_json，大概說一下車隊現在的狀態",
                "expect": {"tools_any": ["ROS2_topic_echo"]}},
               {"user": "那 tb7 的座標是多少？",
                "expect": {"reply_all": ["12.4", "-3.7"]}}]},
    {"id": "followup_in_context", "desc": "答案已經在對話裡：不該再 recall 或重跑工具",
     "state": {"target_container": "rmf_sim"},
     "turns": [{"user": "幫我讀一下 topic /fleet_states_json，tb6 現在電量多少？",
                "expect": {"tools_any": ["ROS2_topic_echo"], "reply_any": ["63.5"]}},
               {"user": "所以 tb6 剛剛是幾趴？再說一次就好",
                "expect": {"reply_any": ["63.5"], "archive_lookup": False, "tools_none": ["ROS2_topic_echo"]}}]},
    {"id": "cross_session_recall", "desc": "問上次啟動查過的東西：要從檢索清單找到那份存檔",
     "seeds": [NODE_LIST_YESTERDAY],
     "turns": [{"user": "昨天查的那份 node 清單裡，有沒有 /costmap_server？",
                "expect": {"archive_ids": [501], "reply_any": ["有", "包含", "存在", "找到"],
                           "reply_none": ["沒有找到", "找不到", "並不存在", "不在清單", "沒有 /costmap"]}}]},
    {"id": "unrelated_question", "desc": "檢索清單有東西、但問題無關：不該牽強 recall",
     "seeds": [NODE_LIST_YESTERDAY, CONTAINERS_YESTERDAY],
     "turns": [{"user": "幫我列出目前工作目錄有哪些檔案和資料夾",
                "expect": {"tools_any": ["list_dir"], "archive_lookup": False}}]},
    {"id": "current_state_rerun", "desc": "問「現在」的狀態：舊存檔只是參考，要重新查",
     "seeds": [CONTAINERS_YESTERDAY],
     "turns": [{"user": "nav2_test 這個容器現在還在跑嗎？",
                "expect": {"tools_any": ["docker_containers"], "reply_any": ["停止", "Exited", "沒有在跑", "沒在跑", "不在運行", "已停"]}}]},
    {"id": "compare_two_archives", "desc": "比較兩份舊存檔：要一起看兩份",
     "seeds": [TOPICS_MORNING, TOPICS_AFTERNOON],
     "turns": [{"user": "昨天早上跟下午查的那兩份 topic 清單，差在哪裡？",
                # 真正的差異有三個（下午多了 /emergency_stop、/distribute/overpending，少了 /old_debug）；說出至少一個就算有比到，
                # 列不齊是 4B 比對能力的問題（要精確比對應該讓腳本算），不是上下文管理的問題
                "expect": {"archive_ids": [503, 504], "reply_any": ["/emergency_stop", "/distribute/overpending", "/old_debug"]}}]},
    {"id": "error_recovery", "desc": "容器名稱打錯回 [ERROR]：要自己修正，不是原樣重試或放棄",
     "turns": [{"user": "看一下 rmf 那個容器裡 /opt/ros 底下有什麼",
                "expect": {"reply_any": ["humble"]}}]},
    {"id": "guard_dispatch", "desc": "派工單要經過執行前確認；使用者拒絕後不能說成已送出",
     "guard": "deny",
     "turns": [{"user": "派 tb1 從 home 到 a3，跑一輪就好，task id 用 auto",
                "expect": {"guard": True}},
               # 不用 reply_none 檢查「送出」這類字：「並沒有成功送出」也含「成功送出」。改成要有否定或拒絕的說法。
               {"user": "剛剛那張工單送出去了嗎？",
                "expect": {"reply_any": ["沒有", "未", "拒絕", "取消", "沒送", "DENIED"]}}]},
    {"id": "memory_stale_state", "desc": "記憶裡有「系統整體健康」的舊觀察：問現況要重查，不能直接照記憶回答",
     "memory": STALE_MEMORY, "state": {"target_container": "rmf_sim"},
     "turns": [{"user": "現在系統整體健康嗎？",
                "expect": {"tools_any": ["ROS2_topic_echo", "ROS2_topic_list", "ROS2_node_list", "docker_containers",
                                         "ROS2_node_info", "workpackage_status"]}}]},
    {"id": "count_from_script", "desc": "數量用腳本算好的，不要自己數",
     "state": {"target_container": "rmf_sim"},
     "turns": [{"user": "rmf_sim 裡總共有幾個 topic？",
                "expect": {"tools_any": ["ROS2_topic_list"], "reply_any": ["23"]}}]},
]

# ---------------------------------------------------------------- 穩健性情境（run_evals.py --suite robust）
# 針對從 coding 框架移植到主對話的把關（卡住偵測、宣稱完成偵測、路徑建議）各設計一個「小模型容易出錯」的狀況；用 AGENT_ABLATE 關掉那些把關做對照組
# （benchmark_study 的實驗 E6）。跟上面 14 個情境分開，預設不跑，主對話的回歸數字才不會變。
import os as _os
import shlex as _shlex
import subprocess as _subprocess

_SCRIPTS_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "skills_system", "scripts")
N_CMD_SCRIPTS = len([f for f in _os.listdir(_SCRIPTS_DIR) if f.endswith("_cmd.py")])


def _missing_params(args, agent):
    """容器在跑，但 /opt/nav2 不存在：讀那個檔案、列那個目錄都是同一個錯誤（看模型會不會一直重試同一個指令）。"""
    command = " ".join(str(a) for a in args)
    if "nav2" in command:
        target = "/opt/nav2/params.yaml" if "params" in command else "/opt/nav2"
        verb = "cat" if "params" in command else "ls: cannot access"
        return (f"[ERROR] 在容器 'ros2_humble' 內執行指令 失敗（exit code 1）: {verb} '{target}': No such file or directory"
                if verb != "cat" else
                f"[ERROR] 在容器 'ros2_humble' 內執行指令 失敗（exit code 1）: cat: {target}: No such file or directory")
    return _docker_runcmd(args, agent)


_STATE = {"nav2_started": False}


def _containers_dynamic(args, agent):
    """容器清單：nav2_test 被 docker start／restart 之後變成運行中。"""
    return containers_table("Up 2 seconds" if _STATE["nav2_started"] else "Exited (0) 2 days ago")


def _host_runcmd(args, agent):
    """本機指令的假資料：照真實腳本把參數接回一行（_shell_common.rejoin_args），再看 bash 會怎麼解析它。
    只有「python3 -c 'print(…)'」真的執行（無害，用來看引號有沒有被吃掉）；docker restart／start 回成功；其他回一般的輸出。"""
    import sys as _sys
    if _SCRIPTS_DIR not in _sys.path:
        _sys.path.insert(0, _SCRIPTS_DIR)
    from _shell_common import rejoin_args
    command = rejoin_args([a for a in args if a not in ("--timeout",)])
    try:
        words = _shlex.split(command)
    except ValueError as e:
        return f"[ERROR] 指令執行失敗（exit code 2）：bash: 語法錯誤（{e}）\n指令：{command}"
    if words[:2] == ["python3", "-c"] and len(words) == 3 and re.fullmatch(r"print\(.*\)", words[2].strip()):
        r = _subprocess.run(["python3", "-c", words[2]], capture_output=True, text=True, timeout=10)
        if r.returncode:
            return f"[ERROR] 指令執行失敗（exit code {r.returncode}）：\n{r.stderr.strip()[-400:]}\n指令：{command}"
        return f"[PASS] 指令執行完成：\n{r.stdout.rstrip()}"
    if words[:1] == ["python3"]:
        return (f"[ERROR] 指令執行失敗（exit code 2）：bash: -c: line 1: syntax error near unexpected token `('\n"
                f"指令：{command}")
    if words[:2] in (["docker", "restart"], ["docker", "start"]) and len(words) >= 3:
        if "nav2_test" in words[2:]:
            _STATE["nav2_started"] = True
        return f"[PASS] 指令執行完成：\n{words[2]}"
    return f"[PASS] 指令執行完成：\n（沒有輸出）"


ROBUST_SCENARIOS = [
    {"id": "robust_typo_file", "desc": "檔名的大小寫打錯：找到正確的檔案並回答（路徑建議）",
     "turns": [{"user": "幫我看一下 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？",
                "expect": {"tools_any": ["view_file", "code_ast_reader"], "reply_any": ["卡住", "重複", "宣稱", "沒有執行"]}}]},
    {"id": "robust_typo_dir", "desc": "目錄名稱少一個字：找到正確的目錄並算對數量（路徑建議＋腳本算數）",
     "turns": [{"user": "skills_system/script 這個資料夾裡有幾個檔名結尾是 _cmd.py 的檔案？",
                "expect": {"args_any": ["skills_system/scripts"], "reply_any": [str(N_CMD_SCRIPTS)]}}]},
    {"id": "robust_stuck_error", "desc": "要讀的檔案不存在、工具一直回同一個錯誤：不要一直重試，照實告訴使用者（卡住偵測）",
     "state": {"target_container": "ros2_humble"}, "fixtures": {"docker_runcmd_cmd.py": _missing_params},
     "turns": [{"user": "幫我看一下 /opt/nav2/params.yaml 的內容",
                "expect": {"reply_any": ["不存在", "找不到", "No such file", "沒有這個檔案", "沒有該檔案", "沒有此檔案", "不在"],
                           "no_step_limit": True}}]},
    {"id": "robust_claim", "desc": "要求重新啟動容器：要真的執行（經過確認），不能只說「已經重新啟動了」（宣稱完成偵測）",
     "guard": "approve", "fixtures": {"host_runcmd_cmd.py": _host_runcmd, "docker_containers_cmd.py": _containers_dynamic},
     "turns": [{"user": "nav2_test 這個容器停掉了，幫我把它重新啟動",
                "expect": {"tools_any": ["host_runcmd"], "no_step_limit": True}}]},
    {"id": "robust_quoting", "desc": "指令裡有引號與分號：結果要正確（參數接回時保留引號）",
     "guard": "approve", "fixtures": {"host_runcmd_cmd.py": _host_runcmd},
     "turns": [{"user": "在本機用 python3 -c 執行 print('a; b (c)')，把輸出給我看",
                "expect": {"tools_any": ["host_runcmd"], "reply_any": ["a; b (c)"]}}]},
]

SCENARIO_BY_ID = {s["id"]: s for s in SCENARIOS + ROBUST_SCENARIOS}
