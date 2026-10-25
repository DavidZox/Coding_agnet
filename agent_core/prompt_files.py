"""prompts/ 底下的範本：讀檔、取一則、填值。給模型的文字都放在 prompts/（改字不用改程式），程式只填算出來的部分。

寫法（prompts/README.md 有完整的說明）：
- `{名稱}`：程式填入的值。只換呼叫時給的名稱，一次換完（填進去的值裡就算有大括號也不會再被換）；其他大括號——JSON 的例子、
  給模型看的 `{名稱}` 佔位符——照原樣留著。
- 一個檔案放好幾則時，每一則用一行 `<!-- @名稱 -->` 開頭，到下一行 `<!-- @… -->` 或檔尾為止；那一則最後的換行都不算
  （每則之間空幾行都一樣；開頭要空一行就在標記下面空一行）。第一個標記之前的文字是給人看的說明，不會送給模型。
- 整個檔案就是一則的（AGENT.md、extract/worker.md…）照檔案原樣讀，不去頭尾。

讀不到（檔案或那一則不存在）回空字串，不讓 harness 因為少一個檔案就停下來；evals/integrity/selftest.py 檢查程式用到的每一則都在、
程式給的名稱範本裡都有。檔案改了就重讀（看修改時間），改 prompt 不用重新啟動。"""
import os
import re
import threading

from .config import PROMPTS_DIR

_MARK = re.compile(r"^<!-- @([\w.-]+) -->[ \t\r]*$", re.M)
_cache = {}
_lock = threading.Lock()


def _read(relpath):
    """prompts/<relpath> 的全文（看修改時間快取）；讀不到回 None。"""
    path = os.path.join(PROMPTS_DIR, relpath)
    try:
        st = os.stat(path)
    except OSError:
        return None
    stamp = (st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _cache.get(path)
        if hit and hit[0] == stamp:
            return hit[1]
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    with _lock:
        _cache[path] = (stamp, text)
    return text


def sections(text):
    """範本全文 → {名稱: 那一則}（每一則最後的換行不算）。"""
    out = {}
    marks = list(_MARK.finditer(text or ""))
    for i, m in enumerate(marks):
        start = m.end() + 1 if text[m.end():m.end() + 1] == "\n" else m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[start:end]
        out[m.group(1)] = body.rstrip("\r\n")
    return out


def fill(text, fields):
    """把 {名稱} 換成值：只換 fields 裡有的名稱，一次換完。"""
    if not fields or not text:
        return text
    pattern = re.compile(r"\{(" + "|".join(re.escape(k) for k in sorted(fields, key=len, reverse=True)) + r")\}")
    return pattern.sub(lambda m: str(fields[m.group(1)]), text)


def load(relpath, section=None, /, **fields):
    """prompts/<relpath>（給 section 就取那一則），{名稱} 換成 fields 的值；讀不到回空字串。"""
    text = _read(relpath)
    if text is None:
        return ""
    if section is not None:
        text = sections(text).get(section)
        if text is None:
            return ""
    return fill(text, fields)


def exists(relpath, section=None, /):
    """範本（或其中一則）在不在——給檢查用。"""
    text = _read(relpath)
    if text is None:
        return False
    return section is None or section in sections(text)
