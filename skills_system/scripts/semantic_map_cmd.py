"""semantic_map：語義地圖與目前佈局——站點（名稱、節點 id、語意名稱）、說明（含 VLM 判讀紀錄）、座標、路段，並用同一幀快照把
機器人（座標最近的站、前往的站、所在路段）與 work package 當前派工的站對到每個站點。

資料全部問 web_console：GET /api/topology（拓譜圖 + semantics.yaml）與 WebSocket /api/ws 一幀快照，不讀任何地圖檔，所以看到的
永遠是 web_console 目前載入的場域。節點的 name 可能是空字串（fih_humanoid_amrScene_v2、BadaMap02 全部都是）：這種站以節點 id
表示（送工作包寫 id 或語意名稱）。不帶參數＝總覽（每站一行、目前有機器人／工作包的站、機器人各一行）；帶關鍵字或站點＝
該站／路段的完整說明與連接路段；--stations／--robots 只列站點或機器人。共用層見 _rmf_common.py。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rmf_common as rc   # noqa: E402

LIST_HITS = 12            # 關鍵字查詢最多列幾個站、幾個路段（其餘寫「另有 N 個」）
LIST_LINKED = 12          # 每站最多列幾條連接路段
DESC_CHARS = 600          # 說明最多列幾個字

USAGE = (
    "用法: scripts/semantic_map_cmd.py [關鍵字或站點] [--stations] [--robots] [--url 位址]\n"
    "  不帶參數：全部站點（名稱｜id｜語意名稱）、目前有機器人／工作包的站點、機器人；帶關鍵字或站點：該站／路段的完整說明。\n"
    "  --stations：只列站點；--robots：只列機器人（名冊＋目前狀態）。"
)


def parse_args(argv):
    """純函式：回傳 dict（error、query、mode：map／stations／robots、url）。"""
    pos, opts, err = rc.parse_cli(argv, values={"--url": "web_console 位址（例如 http://localhost:8020）"}, flags=("--stations", "--robots"),
                                  elsewhere={"--watch": "workpackage_status", "--amr": "workpackage_send"}, usage=USAGE)
    if err:
        return {"error": err}
    if len(pos) > 1:
        return {"error": f"[ERROR] 只接受一個關鍵字，收到 {len(pos)} 個（{'、'.join(pos)}）；含空白的關鍵字請用引號包住。\n{USAGE}"}
    flags = [f for f in ("--stations", "--robots") if opts.get(f)]
    if len(flags) > 1 or (flags and pos):
        return {"error": f"[ERROR] --stations、--robots、關鍵字一次只能用一種。\n{USAGE}"}
    url, err = rc.resolve_url(opts.get("--url"))
    if err:
        return {"error": err}
    return {"error": None, "query": pos[0].strip() if pos else None, "mode": flags[0][2:] if flags else "map", "url": url}


# ---------------------------------------------------------------- 文字
def node_row(n):
    parts = [n["name"] or f"id {n['sid']}"]
    if n["name"]:
        parts.append(f"id {n['sid']}")
    if n["sem"]:
        parts.append(n["sem"])
    return "｜".join(parts)


def counts(topo):
    nodes, edges = topo["nodes"], topo["edges"]
    named = sum(1 for n in nodes if n["name"])
    sem = sum(1 for n in nodes if n["sem"])
    sem_e = sum(1 for e in edges if e.get("label"))
    unnamed = len(nodes) - named
    return (f"{len(nodes)} 站（有名稱 {named}" + (f"、只有 id {unnamed}" if unnamed else "") + f"；有語意名稱 {sem}）、"
            f"{len(edges)} 路段（有語意名稱 {sem_e}）")


def station_rows(topo):
    unnamed = any(not n["name"] for n in topo["nodes"])
    head = f"## 站點（{len(topo['nodes'])} 個：名稱｜節點 id｜語意名稱"
    head += "；沒有名稱的站以 id 表示，送工作包寫 id 或語意名稱）" if unnamed else "）"
    return [head] + [f"- {node_row(n)}" for n in topo["nodes"]]


def _robot_rows(robot_lines):
    return [f"- {rid} {text}" for rid, text in robot_lines]


# ---------------------------------------------------------------- 語義地圖 + 目前佈局
def map_mode(base, query=None):
    topo, err = rc.fetch_topology(base)
    if err:
        if "HTTP 404" in err:
            return err + "\n（這個版本的 web_console 沒有 /api/topology；只要站點清單可以用 semantic_map --stations。）"
        return err
    snapshot, ws_err = rc.ws_read_json(base)
    per_station, robot_lines = rc.occupancy(snapshot, topo) if snapshot else ({}, [])
    live = "web_console /api/topology＋即時快照" if snapshot else f"⚠️ 即時快照讀不到（{rc.clip(ws_err[8:], 100)}），以下沒有機器人／工作包的位置"
    if not query:
        head = f"[PASS] 語義地圖：{counts(topo)}；目前有機器人或工作包的站 {len(per_station)} 個（{live}）"
        if not topo["nodes"]:
            return (f"[ERROR] web_console 的拓譜圖沒有任何站點（/api/topology 回 0 個節點）。下一步：請使用者確認 web_console 載入的場域"
                    f"（map_scenario／map_filename）。")
        lines = [head] + station_rows(topo)
        lines.append(f"## 目前有機器人或工作包的站（{len(per_station)} 個）")
        lines += [f"- {rc.station_text(ref, topo)}：{'；'.join(items)}" for ref, items in per_station.items()] or ["- 沒有"]
        if snapshot:
            lines.append(f"## 機器人（{len(robot_lines)} 台）")
            lines += _robot_rows(robot_lines) or ["- 快照裡沒有機器人"]
            if robot_lines:
                lines.append(rc.BATTERY_NOTE)
        lines.append("（用 semantic_map <關鍵字或站點> 看某站／路段的完整說明與連接路段）")
        return "\n".join(lines)

    q = query.lower()
    m = re.fullmatch(r"(?:id\s*|#)?(\d+)", q)
    qid = m.group(1) if m else None

    def node_rank(n):
        if q == n["name"].lower() or (qid is not None and qid == n["sid"]):
            return 0
        if q == n["sem"].lower():
            return 1
        if len(q) >= 2 and qid is None and q in n["sem"].lower():
            return 2
        if len(q) >= 2 and q in str(n.get("description") or "").lower():
            return 3
        return None

    hit_nodes = sorted((r, i, n) for i, n in enumerate(topo["nodes"]) if (r := node_rank(n)) is not None)
    hit_nodes = [n for _, _, n in hit_nodes]
    hit_edges = []
    for e in topo["edges"]:
        ends = {x.lower() for x in rc._edge_endpoints(e, topo)}
        text = f"{e.get('label') or ''} {e.get('description') or ''}".lower()
        if q in ends or (len(q) >= 2 and qid is None and q in text) or (q.startswith("#") and q[1:] == str(e.get("id"))):
            hit_edges.append(e)
    head = f"[PASS] 語義地圖：{counts(topo)}（{live}）"
    if not hit_nodes and not hit_edges:
        close = rc.close_matches(query, [n["name"] for n in topo["nodes"]] + list(topo["labels"]))
        return (f"[ERROR] 找不到與「{query}」相關的站點或路段（比對了站點名稱、節點 id、語意名稱、說明）"
                + (f"；相近的：{'、'.join(close)}" if close else "")
                + "。下一步：換一個關鍵字，或用 semantic_map --stations 看全部站點。")
    lines = [head, f"## 與「{query}」相關（站點 {len(hit_nodes)} 個、路段 {len(hit_edges)} 條"
             + (f"；各列前 {LIST_HITS} 個" if max(len(hit_nodes), len(hit_edges)) > LIST_HITS else "") + "）"]
    k = 0
    for n in hit_nodes[:LIST_HITS]:
        k += 1
        desc = str(n.get("description") or "")
        lines.append(f"--- #{k} {node_row(n)}｜座標 ({n.get('x')}, {n.get('y')})")
        lines.append(f"  說明：{rc.clip(desc, DESC_CHARS) or '（尚未設定）'}" + (f"（共 {len(desc)} 字，只列前 {DESC_CHARS} 字）" if len(desc) > DESC_CHARS else ""))
        lines.append(f"  目前：{'；'.join(per_station.get(n['ref'], [])) or ('沒有機器人在此或前往、沒有工作包派工中' if snapshot else '（沒有即時快照）')}")
        linked = [e for e in topo["edges"] if n["sid"] in (str(e.get("start_id")), str(e.get("end_id")))]
        if linked:
            lines.append(f"  連接路段（{len(linked)} 條）：" + "；".join(
                f"#{e.get('id')} {'→'.join(rc._edge_endpoints(e, topo))}" + (f"「{e.get('label')}」" if e.get("label") else "")
                for e in linked[:LIST_LINKED]) + (f"…另有 {len(linked) - LIST_LINKED} 條" if len(linked) > LIST_LINKED else ""))
    if len(hit_nodes) > LIST_HITS:
        lines.append(f"- …另有 {len(hit_nodes) - LIST_HITS} 個站點符合：{'、'.join(node_row(n) for n in hit_nodes[LIST_HITS:LIST_HITS + 20])}"
                     + ("…" if len(hit_nodes) > LIST_HITS + 20 else "") + "（用更精確的關鍵字看它們的說明）")
    for e in hit_edges[:LIST_HITS]:
        k += 1
        a, b = rc._edge_endpoints(e, topo)
        desc = str(e.get("description") or "")
        lines.append(f"--- #{k} 路段 #{e.get('id')} {rc.station_text(a, topo)}→{rc.station_text(b, topo)}｜語意名稱：{e.get('label') or '—'}")
        lines.append(f"  說明：{rc.clip(desc, DESC_CHARS) or '（尚未設定）'}" + (f"（共 {len(desc)} 字，只列前 {DESC_CHARS} 字）" if len(desc) > DESC_CHARS else ""))
    if len(hit_edges) > LIST_HITS:
        lines.append(f"- …另有 {len(hit_edges) - LIST_HITS} 條路段符合（用更精確的關鍵字）")
    if robot_lines:
        lines.append(f"## 機器人（{len(robot_lines)} 台）")
        lines += _robot_rows(robot_lines)
    return "\n".join(lines)


# ---------------------------------------------------------------- 站點／機器人清單
def stations_mode(base):
    topo, err = rc.fetch_topology(base)
    if not err:
        if not topo["nodes"]:
            return "[ERROR] web_console 的拓譜圖沒有任何站點（/api/topology 回 0 個節點）。下一步：請使用者確認 web_console 載入的場域。"
        return "\n".join([f"[PASS] 目前場域的站點：{counts(topo)}（web_console /api/topology）"] + station_rows(topo))
    status, data, err2 = rc.http_json("GET", base, "/api/stations")
    if err2:
        return err if status is None else f"{err}\n（/api/stations 也拿不到：{err2[8:]}）"
    items = (data or {}).get("stations") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return f"[ERROR] /api/stations 的回應沒有 stations 清單（{rc.clip(str(data), 120)}）。下一步：確認 --url 指的是 web_console。"
    rows = []
    for it in items:
        if isinstance(it, dict):
            sid, label = str(it.get("id", "")), str(it.get("label") or "")
            rows.append(f"- {label}｜id {sid}" if label and label != sid else f"- id {sid}")
        else:
            rows.append(f"- {it}")
    if not rows:
        return "[ERROR] web_console 的站點清單是空的（/api/stations 回 0 個）。下一步：請使用者確認 web_console 載入的場域。"
    return "\n".join([f"[PASS] 目前場域的站點：{len(rows)} 個（/api/topology 拿不到，改用 /api/stations：只有名稱與 id，沒有語意名稱）",
                      f"## 站點（{len(rows)} 個：名稱｜節點 id）"] + rows)


def robots_mode(base):
    snapshot, ws_err = rc.ws_read_json(base)
    status, data, err = rc.http_json("GET", base, "/api/robots")
    roster = [str(r) for r in (data or {}).get("robots") or []] if not err and isinstance(data, dict) else []
    live = (snapshot or {}).get("robots") or {}
    names = sorted(set(roster) | set(live))
    if not names:
        if err and ws_err:
            return err
        return "[ERROR] web_console 沒有任何機器人（robots.yaml 沒有載入，快照裡也沒有）。下一步：請使用者確認場域的 robots.yaml。"
    topo, _ = rc.fetch_topology(base)
    online = sum(1 for r in live.values() if (r or {}).get("status") == "ONLINE")
    src = ("名冊 /api/robots＋即時快照" if roster and snapshot else "名冊 /api/robots（⚠️ 即時快照讀不到，沒有狀態）" if roster
           else "即時快照（/api/robots 拿不到）")
    lines = [f"[PASS] 目前場域的機器人：{len(names)} 台" + (f"（ONLINE {online}）" if snapshot else "") + f"（{src}）",
             f"## 機器人（{len(names)} 台）"]
    for rid in names:
        info = live.get(rid)
        if info is None:
            lines.append(f"- {rid}" + ("：快照裡沒有它（distribute 沒有它的狀態）" if snapshot else ""))
            continue
        extra = []
        if info.get("target_id"):
            extra.append(f"目標 {rc.station_text(info['target_id'], topo, True)}")
        if info.get("last_task_id") not in (None, "", "None"):
            extra.append(f"最後領取 {info['last_task_id']}")
        lines.append(f"- {rid} {info.get('status', '?')}｜顯示 {info.get('state', '?')}｜自報 {info.get('real_state') or '?'}"
                     + (f"｜{'｜'.join(extra)}" if extra else "") + ("" if rid in roster or not roster else "｜（不在 robots.yaml 名冊）"))
    if names:
        lines.append(rc.BATTERY_NOTE)
    return "\n".join(lines)


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    if p["mode"] == "stations":
        return stations_mode(p["url"])
    if p["mode"] == "robots":
        return robots_mode(p["url"])
    return map_mode(p["url"], p["query"])


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] semantic_map 未預期的例外：{type(e).__name__}: {e}")
        sys.exit(1)
