"""技能規格（skills_system/tools/<名稱>.md）裡給程式看的欄位（寫法見 doc/技能撰寫規範.md）。

frontmatter 的這幾個欄位是給程式看的，值寫成一行 JSON（JSON 也是 YAML，不用 PyYAML 就讀得到）：
- parameters：每個參數怎麼取得——fetch（用哪個技能查，例如 `find_file <檔名>`）或 ask（要使用者決定什麼）；必填的參數一定有其中一個；
- receipt：腳本收據（skills_system/scripts/_receipt_common.py）的欄位：counts、items 的鍵與其他欄位，後面加 ? 的是不一定有的；
- narrow：逾時（還沒有任何結果）時第 1 級可以怎麼縮小範圍——腳本 parse_args 結果的鍵 → 規則（inside：路徑換成原本路徑裡面的；
  added：清單多加幾項），低階執行器（agent_core/edg.py）核對修正只動了這些。沒寫的工具逾時就往上報。
- listing：`true`＝輸出是程式整理好的清單（每一行一筆、附路徑或行號，總數也是程式算的）：超過工具回傳門檻、但放得進一段時直接給原文、
  不提煉（agent_core/turn.py 的 listing_raw；照存檔的收據寫的技能認）。
- live：`true`＝查的是執行中系統當下的狀態（容器、ROS 2、調度系統的查詢）：存檔是那時候的狀態，檢索清單與讀回時程式寫明是什麼時候查的、
  領域 session 的回報引用了這一回合之前的就交回一次（框架討論紀錄第 42、43 輪；skills_system/scripts/_results_common.py 的 memory_kind、archive_facts）。
載入規格給模型看時拿掉這幾行（for_model），模型讀到的跟以前一樣。

有骨架的技能（skills_system/<領域>/<名稱>.md，agent_core/composite.py 讀；寫法見 doc/技能撰寫規範.md）另外有：
- frontmatter 的 topology（一行 JSON：depends_on、sub_skills）、parameters 與 answers（答得了問題要的哪幾種：位置、數量、內容）；
- 正文的〈骨架〉（決策圖的樣板）與〈回退〉（第 2 級的做法）：各是一個 ```json 區塊，給程式看；
交給模型時這兩節也拿掉（for_model），模型只讀〈什麼時候用〉與〈策略與 SOP〉。
"""
import json
import re

_MACHINE = re.compile(r"^(parameters|receipt|narrow|listing|live|topology|answers):\s*(.*)$")
_EXECUTE = re.compile(r"EXECUTE:\s*scripts/([A-Za-z0-9_]+\.py)")
MACHINE_SECTIONS = ("骨架", "回退")      # 複合技能正文裡給程式看的章節
_FENCE = re.compile(r"^\s*```")
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n\s*```", re.S)


def _split(text):
    """(frontmatter 的各行, frontmatter 之後的文字，從結尾的 \\n--- 開始)；沒有 frontmatter 回 (None, text)。"""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    return text[4:end].split("\n"), text[end:]


def for_model(text):
    """給模型看的規格：拿掉 frontmatter 裡給程式看的欄位與正文裡給程式看的章節（〈骨架〉〈回退〉）；沒有這些時原文照回。"""
    head, rest = _split(text)
    if head is None:
        return text
    return "---\n" + "\n".join(ln for ln in head if not _MACHINE.match(ln)) + _drop_sections(rest, MACHINE_SECTIONS)


def _headings(lines):
    """正文裡 `# 標題` 的 (行的位置, 標題)；程式碼區塊裡的 # 不算。"""
    out, fenced = [], False
    for i, ln in enumerate(lines):
        if _FENCE.match(ln):
            fenced = not fenced
        elif not fenced and ln.startswith("# "):
            out.append((i, ln[2:].strip()))
    return out


def _drop_sections(rest, names):
    lines = rest.split("\n")
    heads = _headings(lines)
    drop = set()
    for k, (i, title) in enumerate(heads):
        if title in names:
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            drop.update(range(i, end))
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def sections(text):
    """正文的 `# 標題` → 那一節的內容（去頭尾空白）。"""
    _, rest = _split(text)
    lines = rest.split("\n")
    heads = _headings(lines)
    out = {}
    for k, (i, title) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        out[title] = "\n".join(lines[i + 1:end]).strip()
    return out


def composite(text):
    """複合技能的規格 → {"meta": {type, title, description, version}, "topology", "parameters", "answers", "skeleton", "fallbacks", "sections"}。
    給程式看的 JSON（frontmatter 的欄位、〈骨架〉〈回退〉的 json 區塊）寫錯時丟 ValueError。"""
    head, _ = _split(text)
    if head is None:
        raise ValueError("沒有 frontmatter（--- 開頭的那幾行）")
    meta = {}
    for ln in head:
        if ":" in ln and not _MACHINE.match(ln):
            k, v = ln.split(":", 1)
            meta[k.strip()] = v.strip()
    machine = contract(text)
    secs = sections(text)
    blocks = {}
    for name in MACHINE_SECTIONS:
        m = _JSON_BLOCK.search(secs.get(name, ""))
        if not m:
            raise ValueError(f"〈{name}〉沒有 ```json 區塊")
        try:
            blocks[name] = json.loads(m.group(1))
        except ValueError as e:
            raise ValueError(f"〈{name}〉的 JSON 寫錯了：{e}") from e
    return {"meta": meta, "topology": machine.get("topology"), "parameters": machine.get("parameters"), "answers": machine.get("answers"),
            "skeleton": blocks["骨架"], "fallbacks": blocks["回退"], "sections": secs}


def contract(text):
    """規格裡給程式看的欄位 → {"parameters": [...], "receipt": {...}, "narrow": {...}, "listing": true, "live": true}；沒寫的不在結果裡。JSON 寫錯時丟 ValueError。"""
    head, _ = _split(text)
    out = {}
    for ln in head or []:
        m = _MACHINE.match(ln)
        if m:
            out[m.group(1)] = json.loads(m.group(2))
    return out


def script(text, skill):
    """這個技能執行的腳本檔名：規格提到 scripts/<技能>_cmd.py 就是它，不然是〈語法〉第一個 `EXECUTE: scripts/<x>.py`
    （list_dir＝ls_cmd.py、view_file＝cat_cmd.py…；跟 trajectory._script_skill_map 同一個規則）。找不到回 None。"""
    own = f"{skill}_cmd.py"
    if f"scripts/{own}" in text:
        return own
    m = _EXECUTE.search(text)
    return m.group(1) if m else None
