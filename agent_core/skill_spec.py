"""技能規格（skills_system/tools/<名稱>.md）裡給程式看的欄位（新架構 D6、D4；寫法見 doc/技能撰寫規範.md）。

frontmatter 的兩個欄位是給程式看的，值寫成一行 JSON（JSON 也是 YAML，不用 PyYAML 就讀得到）：
- parameters：每個參數怎麼取得——fetch（用哪個技能查，例如 `find_file <檔名>`）或 ask（要使用者決定什麼）；必填的參數一定有其中一個；
- receipt：腳本收據（skills_system/scripts/_receipt_common.py）的欄位：counts、items 的鍵與其他欄位，後面加 ? 的是不一定有的。
載入規格給模型看時拿掉這兩行（for_model），模型讀到的跟以前一樣。
"""
import json
import re

_MACHINE = re.compile(r"^(parameters|receipt):\s*(.*)$")


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
    """規格裡給程式看的欄位 → {"parameters": [...], "receipt": {...}}；沒寫的不在結果裡。JSON 寫錯時丟 ValueError。"""
    head, _ = _split(text)
    out = {}
    for ln in head or []:
        m = _MACHINE.match(ln)
        if m:
            out[m.group(1)] = json.loads(m.group(2))
    return out
