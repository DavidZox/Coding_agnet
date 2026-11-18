"""真實專案評測的核對：拿 agent 最後的回覆對答案（evals/repo/answers.json 的 items、forbid）。

一則事實（item）是幾組寫法：每一組都要在回覆裡出現（組內任一個寫法就算）。
- file：第一組是檔名，其他組要跟它寫在同一行，或寫在它後面、下一個檔名出現之前（最多 300 字）——檔名與行號、檔名與次數，
  「x.py:82」「檔案：x.py」換行「第 82 行」都算，下一個檔案的數字不會算到前一個；
- line：這幾組要寫在同一行（參數與預設值、總數）；
- near：這幾組要在 near 個字以內（規格書的編號與它的內容，說明可能換行）。
比對的規則：
- 數字前後不能接數字或小數（28 不會對到 128、2.8、28.5）；
- 名稱、檔名前後不能接英數字或底線（odom 不會對到 odom_frame_id，registry.py 不會對到 fleet_registry.py）；
- `/` 開頭的 topic 前後不能接名稱的字元或 `/`（/scan 不會對到 /scan_merged、/front/scan）；
- 英文不分大小寫；中文照字面。
- `re:` 開頭的寫法是正規表示式（不分大小寫、不加邊界）：中文的說法（「不會進行回報」「仍會成功」）與接在名稱裡的字
  （`ekf_filter_node` 裡的 ekf、`use_rmf_speed_limit` 裡的 rmf）用這個。
forbid 出現就算錯（例如限定範圍的題目答成整個目錄的總數）。碰到確認關卡也算錯：題目都是唯讀的，評測時關卡一律拒絕，
那一題就停在那裡（唯讀清單外的指令也會碰到，例如用 host_runcmd 跑 find；找檔案有 find_file）。
"""
import re

_W = "A-Za-z0-9_"
_FILE = re.compile(r"[\w./-]+\.(?:py|cpp|cc|hpp|h|md|yaml|yml|launch|xml|json|txt)\b", re.I)
FILE_SPAN = 300


def _rx(token):
    if token.startswith("re:"):
        return re.compile(token[3:], re.I)
    t = re.escape(token)
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return re.compile(rf"(?<![\d.]){t}(?!\d|\.\d)")
    if token.startswith("/"):
        return re.compile(rf"(?<![{_W}/.-]){t}(?![{_W}/-])", re.I)
    pre = rf"(?<![{_W}])" if re.match(rf"[{_W}]", token) else ""
    post = rf"(?![{_W}])" if re.match(rf"[{_W}]", token[-1]) else ""
    return re.compile(pre + t + post, re.I)


def positions(text, group):
    """一組寫法在 text 裡出現的位置（任一個寫法）。"""
    return sorted({m.start() for alt in group for m in _rx(alt).finditer(text)})


def _after_file(text, groups):
    """第一組（檔名）的每一處：它後面到下一個檔名之前（最多 FILE_SPAN 字）有沒有其他每一組。"""
    for alt in groups[0]:
        for m in _rx(alt).finditer(text):
            nxt = _FILE.search(text, m.end())
            span = text[m.end():min(nxt.start() if nxt else len(text), m.end() + FILE_SPAN)]
            if all(positions(span, grp) for grp in groups[1:]):
                return True
    return False


def item_ok(text, it):
    if it.get("file"):
        return item_ok(text, {"all": it["all"], "line": True}) or _after_file(text, it["all"])
    if it.get("line"):
        return any(item_ok(ln, {"all": it["all"]}) for ln in text.split("\n"))
    pos = [positions(text, grp) for grp in it["all"]]
    if any(not p for p in pos):
        return False
    w = it.get("near")
    if not w:
        return True
    return any(all(any(abs(q - p0) <= w for q in ps) for ps in pos[1:]) for p0 in pos[0])


def final_reply(out):
    """worker 輸出裡 agent 最後給使用者的回覆：最後一步沒有動作的那則回覆；沒有就用最後一則回覆。"""
    for turn in reversed(out.get("turns") or []):
        for step in reversed(turn.get("steps") or []):
            if step.get("reply") and not step.get("action"):
                return step["reply"]
    replies = out.get("replies") or []
    return replies[-1] if replies else ""


def score(q, reply, guards=0):
    items = [{"label": it["label"], "ok": item_ok(reply, it)} for it in q["items"]]
    forbidden = [it["label"] for it in q.get("forbid") or [] if item_ok(reply, it)]
    if guards:
        forbidden.append(f"碰到確認關卡 {guards} 次（題目是唯讀的）")
    ok = sum(1 for x in items if x["ok"])
    return {"passed": ok == len(items) and not forbidden, "checks_passed": ok, "checks_total": len(items),
            "items": items, "forbidden": forbidden}
