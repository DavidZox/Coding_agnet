"""提煉（工具回傳的任務導向提煉、result_recall；agent_core/extract.py）的真模型評測情境：程式產生已知答案的長輸出，答案散在全文。

亂數種子固定，同一個情境每次產生一模一樣的輸出（第 2 階段驗證用的就是這幾份：車隊 40／80／120 台、20 萬字的 Log）。每個情境：
  text      工具的原始輸出（照技能的格式：[PASS] 第一行＋內容）
  script／args  假裝是哪一支技能產生的（存檔、檢索清單用）
  question  使用者的問題（錨點）；step：這一步的目的（決策模型的 thought／action）
  truth     正確答案：[{"key": 名稱或時間戳, "value": 值或 None}]
  match     怎麼在回答裡找答案：fleet（名稱＋電量同一行）／name（名稱）／text（字串）
  recall    有的話是追問：先照 text 提煉一次，再用 result_recall 問這一句（同一份存檔）"""
import random

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


def all_cases():
    """fleet_40：一段就放得下（一次寫完）；fleet_80：小模型一次讀會漏、切 2 段；fleet_120：切 3 段；log_200k：切 26 段、依問題挑 8 段讀；
    recall_fleet_120：追問同一份存檔裡提煉沒寫到的。"""
    return [fleet_low_battery(40), fleet_low_battery(80), fleet_low_battery(120), long_log(), fleet_recall(120)]
