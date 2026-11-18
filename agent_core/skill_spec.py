"""技能規格（skills_system/tools/<名稱>.md）裡給程式看的欄位（新架構 D6、D4、D5；寫法見 doc/技能撰寫規範.md）。

frontmatter 的這幾個欄位是給程式看的，值寫成一行 JSON（JSON 也是 YAML，不用 PyYAML 就讀得到）：
- parameters：每個參數怎麼取得——fetch（用哪個技能查，例如 `find_file <檔名>`）或 ask（要使用者決定什麼）；必填的參數一定有其中一個；
- receipt：腳本收據（skills_system/scripts/_receipt_common.py）的欄位：counts、items 的鍵與其他欄位，後面加 ? 的是不一定有的；
- narrow：逾時（還沒有任何結果）時第 1 級可以怎麼縮小範圍——腳本 parse_args 結果的鍵 → 規則（inside：路徑換成原本路徑裡面的；
  added：清單多加幾項），低階執行器（agent_core/edg.py）核對修正只動了這些。沒寫的工具逾時就往上報。
載入規格給模型看時拿掉這幾行（for_model），模型讀到的跟以前一樣。
"""
import json
import re

_MACHINE = re.compile(r"^(parameters|receipt|narrow):\s*(.*)$")
_EXECUTE = re.compile(r"EXECUTE:\s*scripts/([A-Za-z0-9_]+\.py)")


def _split(text):
    """(frontmatter 的各行, frontmatter 之後的文字，從結尾的 \\n--- 開始)；沒有 frontmatter 回 (None, text)。"""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    return text[4:end].split("\n"), text[end:]


def for_model(text):
    """給模型看的規格：拿掉 frontmatter 裡給程式看的欄位；沒有這些欄位時原文照回。"""
    head, rest = _split(text)
    if head is None:
        return text
    return "---\n" + "\n".join(ln for ln in head if not _MACHINE.match(ln)) + rest


def contract(text):
    """規格裡給程式看的欄位 → {"parameters": [...], "receipt": {...}, "narrow": {...}}；沒寫的不在結果裡。JSON 寫錯時丟 ValueError。"""
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
