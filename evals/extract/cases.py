"""提煉（工具回傳的任務導向提煉、result_recall；agent_core/extract.py）的真模型評測情境：程式產生已知答案的長輸出，答案散在全文。

亂數種子固定，同一個情境每次產生一模一樣的輸出（第 2 階段驗證用的就是這幾份：車隊 40／80／120 台、20 萬字的 Log）。每個情境：
  text      工具的原始輸出（照技能的格式：[PASS] 第一行＋內容）
  script／args  假裝是哪一支技能產生的（存檔、檢索清單用）
  question  使用者的問題（錨點）；step：這一步的目的（決策模型的 thought／action）
  truth     正確答案：[{"key": 名稱或時間戳, "value": 值或 None}]
  match     怎麼在回答裡找答案：fleet（名稱＋電量同一行）／name（名稱）／text（字串）
  recall    有的話是追問：先照 text 提煉一次，再用 result_recall 問這一句（同一份存檔）
  texts     有的話是好幾份短輸出（[{text, task}]，取代 text）：照順序存檔（短的不提煉），再用 result_recall 一起問 question
  score_on  answer＝只看提煉的回答那一行（「回答：」；列出的事實不算）；others＝不是答案的名稱（回答寫了算多列的）；
            count_claims＝False 時不核對回答裡「共 N 個」的說法（說的是清單的總數，不是答案的個數）"""
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

FLEET_THRESHOLD = 40


def _fleet(n, seed=7):
    """車隊狀態（ROS2_topic_echo 讀到的 YAML）。每台 11 行；電量、模式、樓層、座標隨機。回傳 (行, 每台的資料)。"""
    rnd = random.Random(seed)
    lines = [f"[PASS] '/fleet_states_json' 的一筆訊息（{n} 台車；等了 0.12 秒）：", "fleet_name: amr_fleet", "robots:"]
    robots = []
    for i in range(1, n + 1):
        bat = round(rnd.uniform(15, 95), 1)
        mode = rnd.choice(["IDLE", "MOVING", "CHARGING", "PAUSED"])
        level = f"L{i % 3 + 1}"
        robots.append({"name": f"amr_{i:02d}", "battery": bat, "mode": mode, "level": level})
        lines += [f"- name: amr_{i:02d}", f"  mode: {mode}", f"  task_id: WP-{1000 + i}", "  location:", f"    level_name: {level}",
                  f"    x: {rnd.uniform(-20, 20):.3f}", f"    y: {rnd.uniform(-20, 20):.3f}", f"    yaw: {rnd.uniform(-3.14, 3.14):.3f}",
                  f"  battery_percent: {bat}", "  issues: []", f"  last_seen_sec_ago: {rnd.randint(0, 5)}"]
    return lines, robots


def fleet_low_battery(n):
    lines, robots = _fleet(n)
    return {"id": f"fleet_{n}", "kind": "fleet", "text": "\n".join(lines), "script": "ROS2_topic_echo_cmd.py", "args": ["/fleet_states_json"],
            "question": f"哪幾台車的電量低於 {FLEET_THRESHOLD}%？",
            "step": {"thought": "看每台車的 battery_percent", "action": {"command": "scripts/ROS2_topic_echo_cmd.py", "args": "/fleet_states_json"}},
            "truth": [{"key": r["name"], "value": r["battery"]} for r in robots if r["battery"] < FLEET_THRESHOLD], "match": "fleet"}


def fleet_recall(n):
    """同一份車隊輸出，先問電量（提煉一次、存檔），再用 result_recall 追問提煉沒寫到的：L2 樓層而且 IDLE 的車。"""
    case = fleet_low_battery(n)
    _, robots = _fleet(n)
    case.update({"id": f"recall_fleet_{n}", "match": "name",
                 "recall": "L2 樓層而且狀態是 IDLE 的車有哪幾台？",
                 "truth": [{"key": r["name"], "value": None} for r in robots if r["level"] == "L2" and r["mode"] == "IDLE"]})
    return case


def long_log(n_lines=3000, seed=3):
    """docker_ctl logs 的 3000 行（約 20 萬字）：50 個 node 的 heartbeat，planner 的 6 筆錯誤散在中段（切段後要挑對段落）。"""
    rnd = random.Random(seed)
    nodes = [f"node_{i:02d}" for i in range(50)]
    lines = [f"[PASS] docker_ctl logs nav_stack：最後 {n_lines} 行（stdout＋stderr，時間是 UTC）", f"## 最後 {n_lines} 行原文"]
    truth = []
    for i in range(n_lines):
        t = 1791967507 + i * 0.5
        if i in (700, 1300, 1301, 1900, 2400, 2650):
            lines.append(f"[ERROR] [{t:.3f}] [planner]: plan failed: goal {i % 7} unreachable (code {300 + i % 5})")
            truth.append({"key": f"{t:.3f}", "value": None})
        else:
            lines.append(f"[INFO] [{t:.3f}] [{rnd.choice(nodes)}]: heartbeat seq={i} load={rnd.uniform(0, 1):.2f} ok")
    return {"id": "log_200k", "kind": "log", "text": "\n".join(lines), "script": "docker_ctl_cmd.py", "args": ["logs", "nav_stack", "--tail", str(n_lines)],
            "question": "planner 出了哪些錯誤？什麼時候？",
            "step": {"thought": "看 planner 的錯誤", "action": {"command": "scripts/docker_ctl_cmd.py", "args": f"logs nav_stack --tail {n_lines}"}},
            "truth": truth, "match": "text"}


def robot_heading():
    """ROS2_topic_echo 觀察 5 秒的 robot_state（2026-10-24 維運評測 ros_moving 的真實輸出，約 6 千字一段，fixtures/robot_state_moving.txt）：
    問「有在移動嗎？往哪裡走？」，要答出要去的站（target_id、current_edge 都是 a7）——那一次的提煉只寫了座標往哪個方向增加，
    主對話就答不出往哪一站。"""
    with open(os.path.join(HERE, "fixtures", "robot_state_moving.txt"), encoding="utf-8") as f:
        text = f.read()
    return {"id": "robot_heading", "kind": "echo", "text": text, "script": "ROS2_topic_echo_cmd.py",
            "args": ["--duration", "5", "/tb1/robot_state"], "question": "觀察 tb1 的 robot_state 大約 5 秒，它有在移動嗎？往哪裡走？",
            "step": {"thought": "讀 tb1 的 robot_state 幾秒，看位置有沒有變、要去哪裡",
                     "action": {"command": "scripts/ROS2_topic_echo_cmd.py", "args": "--duration 5 /tb1/robot_state"}},
            "truth": [{"key": "a7", "value": None}], "match": "text"}


def compare_nodes():
    """yard_sim 上午、下午各查一次 node 清單（各約 30 行、加起來放得進一段），一起 recall、問兩次差在哪裡：下午多了 /pallet_scanner 與
    /agv_5/bumper_watch、少了 /legacy_relay。每一份各自一段、各一個 worker 時，各自只看得到自己那一份，比不出差異（2026-11-24 主對話評測
    compare_two_archives 0／4；設計筆記 2.66）。只看回答那一行：列出的事實把兩份的名稱都列了，不代表比過。"""
    root = ["/yard_dispatcher", "/map_keeper", "/traffic_light_bridge", "/door_gateway", "/lift_gateway", "/charger_monitor"]
    robot = ["controller_server", "planner_server", "bt_navigator", "amcl", "lidar_driver", "battery_monitor"]
    am = root + ["/legacy_relay"] + [f"/agv_{k}/{n}" for k in (3, 5, 8) for n in robot]
    pm = root + ["/pallet_scanner"] + [f"/agv_{k}/{n}" for k in (3, 5, 8) for n in robot + (["bumper_watch"] if k == 5 else [])]

    def listing(names):
        groups = {}
        for n in names:
            groups.setdefault(n.rsplit("/", 1)[0] or "/", []).append(n)
        lines = [f"[PASS] 容器 'yard_sim' 的 node：共 {len(names)} 個；ROS_DOMAIN_ID 12（shell 的設定：容器的環境變數或 ~/.bashrc）"]
        for ns, items in groups.items():
            lines.append(f"## {ns}（根命名空間，{len(items)} 項）" if ns == "/" else f"## {ns}（{len(items)} 項）")
            lines += items
        return "\n".join(lines)

    diff = ["/pallet_scanner", "/agv_5/bumper_watch", "/legacy_relay"]
    return {"id": "compare_nodes", "kind": "compare", "script": "ROS2_node_list_cmd.py", "args": ["yard_sim"],
            "texts": [{"text": listing(am), "task": "上午看一下 yard_sim 有哪些 node"},
                      {"text": listing(pm), "task": "下午再看一次 yard_sim 的 node"}],
            "question": "yard_sim 上午和下午各查了一次 node，兩次有什麼不一樣？",
            "truth": [{"key": n, "value": None} for n in diff], "match": "name", "score_on": "answer",
            "others": sorted(set(am) & set(pm)), "count_claims": False}


def compare_flat():
    """跟 compare_nodes 一樣是兩份短的 node 清單一起 recall、問差在哪裡，但只有根命名空間：清單不分節（ROS2_node_list 只有一個命名空間時
    不加標題），每一份的 worker 沒辦法把一節寫成一條，列不完名稱就只寫總數（compare_nodes 分節，改之前的 26b 每一份的 worker 把一節寫成一條、
    名稱都在裡面，整合照樣比得出來，3／3；設計筆記 2.66）。下午多了 /pallet_scanner 與 /bumper_watch、少了 /legacy_relay。"""
    base = ["/yard_dispatcher", "/map_keeper", "/traffic_light_bridge", "/door_gateway", "/lift_gateway", "/charger_monitor",
            "/route_planner", "/zone_manager", "/fleet_bridge", "/task_board", "/alarm_center", "/camera_hub", "/weather_feed",
            "/conveyor_link", "/shelf_tracker", "/rack_mapper", "/gate_guard", "/visitor_log", "/power_meter", "/clock_sync",
            "/parcel_router", "/light_switch"]
    am = base[:12] + ["/legacy_relay"] + base[12:]
    pm = base[:7] + ["/pallet_scanner"] + base[7:18] + ["/bumper_watch"] + base[18:]

    def listing(names):
        return "\n".join([f"[PASS] 容器 'yard_sim' 的 node：共 {len(names)} 個；ROS_DOMAIN_ID 12（shell 的設定：容器的環境變數或 ~/.bashrc）"] + names)

    diff = ["/pallet_scanner", "/bumper_watch", "/legacy_relay"]
    return {"id": "compare_flat", "kind": "compare", "script": "ROS2_node_list_cmd.py", "args": ["yard_sim"],
            "texts": [{"text": listing(am), "task": "上午看一下 yard_sim 有哪些 node"},
                      {"text": listing(pm), "task": "下午再看一次 yard_sim 的 node"}],
            "question": "yard_sim 上午和下午各查了一次 node，兩次有什麼不一樣？",
            "truth": [{"key": n, "value": None} for n in diff], "match": "name", "score_on": "answer",
            "others": base, "count_claims": False}


def all_cases():
    """fleet_40：一段就放得下（一個 worker 讀全部）；fleet_80：小模型一次讀會漏、切 2 段；fleet_120：切 3 段；log_200k：切 26 段、依問題挑 8 段讀；
    recall_fleet_120：追問同一份存檔裡提煉沒寫到的；robot_heading：一段就放得下，但答案（要去哪一站）不在數值變化裡，要看問題挑欄位；
    compare_nodes／compare_flat：兩份短的一起 recall、比較差異（加起來放得進一段，一個 worker 一起讀；flat 是不分節的清單）。"""
    return [fleet_low_battery(40), fleet_low_battery(80), fleet_low_battery(120), long_log(), fleet_recall(120), robot_heading(), compare_nodes(),
            compare_flat()]
