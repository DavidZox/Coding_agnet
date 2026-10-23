"""模型寫的句子跟程式量到的事實核對「意思」：worker 的說明、Synthesizer 的重點、主對話依數據分析報告的回答共用。

analysis_job._check_note 核對編號、用詞、時間；這裡核對句子說了什麼（實測 lidar：重點寫「/diagnostics_agg 整段沒有變化」「+20.51s
/system/safety_command 的狀態與數值回到初始狀態」，主對話寫「/diagnostics 的 status.level 從 0 變為 2（E6）」——都通過了原本的核對）：
1. 變化：「mode 從 NORMAL 變成 LIMITED」「level：0 → 2」「primary_reaction 變為 HARD_STOP」→ 引用的事件裡要有這個 Key 的這個變化
   （引用 T#＝那個 Topic 全部的變化；句子寫了 Topic 名稱、但沒有引用它的事件＝那個 Topic 全部的變化）。
2. 某一刻的值：「error_code 為 0x04100101」→ 引用的那一刻之前或之後的值；句子寫的是到數據結束（「到最後」「數據結束時」）→ 最後的值。
3. 沒有變化：「/diagnostics_agg 整段沒有變化」「mode 之後沒有再改變」→ 那個 Topic（或 Key）在那段時間真的沒有變化。
4. 回到初始：「…的狀態與數值回到初始狀態」→ 那一刻之後，那個 Topic（或寫到的 Key）每個變過的項目都等於開頭的值
   （中途才出現的項目不算：它沒有錄製開始時的值）。
主詞寫得出來才核對：事實裡的 Key 名稱（mode、status.level、error_code…）、Topic 名稱（/cmd_vel），或這一則引用的編號（E#、T#）。
中文的主詞（「安全閘」「狀態層級」）、部分的說法（其餘、其他項目）、疑問與條件句、否定的「沒有回到初始」不核對；寫明的例外
（「…回到開頭的值，但 primary_reaction 仍是 HARD_STOP」）不算進「回到初始」——只會漏抓，不會把對的擋掉。
值的比對：數字照數值比；文字不分大小寫，可以只寫開頭（事實裡長的值會截短，模型也常只抄開頭）。
資料是 analysis_job.build_facts 整理的 facts：每個 Topic 的 values（每個 Key 開頭與最後的值、每一次變化的 +秒與前後的值、
有沒有變過、是不是中途才出現）、events、topics。"""
import json
import re

_EPS = 0.0015    # 同一則訊息：事件與變化的時間都是 +秒取到小數 3 位，從同一個時間戳算出來

_KEY = r"(?<![/A-Za-z0-9_.\[])(?P<key>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*(?:\[[^\]\n]*\])?)"
# 值：清單、引號裡的文字、或一個 ASCII 的詞（後面可以再接一個小寫的英文字：「LiDAR disconnected」）
_VAL = r"\[[^\]\n]*\]|「[^」\n]*」|\"[^\"\n]*\"|[A-Za-z0-9_.:+\-/<>]+(?: [a-z]+)?"
_TO_WORDS = "變成|變為|變回|轉為|轉成|改為|改成|切換為|切換到|切換成|跳轉為|跳轉到|跳到|降為|降到|降至|升為|升到|升至|增加到|增加為|減少到|減少為|回到|回復到|恢復為|恢復到|恢復成|成為"
_TO = "(?:" + _TO_WORDS + ")"
_FROM_TO = re.compile(_KEY + r"\s*(?:的值|的狀態|的設定)?\s*(?:從|由)\s*(?P<a>" + _VAL + r")\s*(?:（[^）\n]*）|\([^)\n]*\))?\s*(?:" + _TO_WORDS
                      + r"|到)\s*(?P<b>" + _VAL + ")")
_ARROW = re.compile(_KEY + r"\s*[：:=]?\s*(?P<a>" + _VAL + r")\s*(?:→|->|⇒|➔)\s*(?P<b>" + _VAL + ")")
_TO_ONLY = re.compile(_KEY + r"\s*(?:的值|的狀態)?\s*(?:也|同時|則|隨之|跟著|再|又|都|皆|均|已經|已)?\s*" + _TO + r"\s*(?P<b>" + _VAL + ")")
_IS = re.compile(_KEY + r"\s*(?:的值|的狀態)?\s*(?:仍然|仍|依然|還是|還|一直|都|也|皆|均)?\s*(?:是|為|＝|=|維持在|維持|保持在|保持|停在|處於)\s*(?P<b>"
                 + _VAL + ")")
_END = re.compile(r"到(?:數據|錄製)?(?:結束|最後)|(?:數據|錄製)結束(?:時|前|為止)?|最後(?:的值|一則|仍|還|都|是|為)|直到(?:數據|錄製)?結束|整段最後")
_NO_CHANGE = re.compile(r"(?:沒有|未|無|並未)(?:任何|再|再有)?(?:變化|改變|變動)|(?:維持|保持)不變|都沒(?:有)?變|整段不變|不再(?:變化|改變|變動)")
_AFTER = re.compile(r"之後|此後|後來|以後|從此|再|(?<!最)後(?:維持|保持|一直|都|仍|就)")   # 「變為 HARD_STOP 後維持不變」
_LATER = re.compile(r"(?<!最)後|之後|以後")   # 「恢復發布後 linear.x 為 0.0」：說的是那一刻之後的值
# 「數值沒有變化」「所有項目皆沒有變化」說的是值：只算值的變化（只發了一則訊息、開始發布不算）；「整段沒有變化」＝沒有任何事件
_VALUE_SCOPE = re.compile(r"數值|值|狀態|內容|欄位|項目|資料")
_BACK = re.compile(r"(?:回到|回復到?|恢復(?:到|為|成)?)(?:錄製)?(?:初始|開頭|原本|原來|原先|最初|一開始|開始時)")
_NOT_BACK = re.compile(r"(?:沒有|沒|未|並未|尚未|未能|無法|並沒有|不會|不)(?:再|完全|全部|都)?\s*$")   # 「沒有回到初始」「並未恢復到開頭的值」：說的是相反的事
# 寫明的例外：「…最後回到開頭的值，但 primary_reaction 仍是 HARD_STOP」——寫到的 Key、Topic、值不算進同一句的「回到初始」
_EXCEPT = re.compile(r"^\s*(?:但|不過|只是|然而|唯|惟|卻)")
_MID_EXCEPT = re.compile(r"(?<=[^，,；;。\s])\s*(?=但|然而)")   # 子句中間的「但」（「…回到初始值（mode、…）但 reset_request_count 與開頭不同」）也是例外的開始
# 整句裡有就不核對「沒有變化」「回到初始」；「回到開頭的值 4 項」（照抄事實的「變過又回到開頭的值 N 項」）說的是其中幾項，也是部分的說法
_PARTIAL = re.compile(r"其餘|其他|其它|另外|以外|之外|除了|除|部分|大部分|多數|大多|等項目|等欄位|僅|只有|中的|\d+\s*項")
_BEFORE_STOP = re.compile(r"(?:停止(?:發布)?|中斷|斷訊)(?:之)?前")   # 「在停止發布前沒有變化」：說的是停止（或中斷）之前的值
# 句子自己寫出的發布事件（「在發布期間沒有變化，最後停止發布」）：「沒有變化」說的是其他的變化，那幾種事件不算
_DESCRIBED = ((re.compile(r"停止"), ("stop",)), (re.compile(r"中斷|斷訊"), ("gap", "resume")), (re.compile(r"恢復"), ("resume",)),
              (re.compile(r"開始發布|第一則"), ("start", "first")), (re.compile(r"發布期間|發布的期間|發布時"), ("start", "first", "stop")))
_PRED = re.compile(r"(?:是|為|＝|=)\s*[^\s、，,；;。]+")   # 「data 為 FAIL、/T16、/T17 整段沒有變化」：「沒有變化」的主詞在最後一個「為 X」後面
_BACK_ALT = re.compile(r"(?:的)?(?:值|狀態|數值)?\s*(?:或|或是)")   # 「回到初始值或變更」：列舉
# 「相關數值回到初始值」「變動過的項目都回到開頭」：只說那一刻變過的項目——只核對那幾項
_RESTRICT = re.compile(r"相關|這些|那些|變動過|變過的|有變的|改變的|有變化的|多項|幾項|一些")
_ALTERNATIVE = re.compile(r"\s*(?:或|或是|／|/)")   # 「皆為 0 或空值」：列舉幾種可能，不是說它是哪一個
_HEDGE = re.compile(r"是否|有沒有|是不是|如果|若|假如|可能|不確定|無法判斷|看不出|嗎")
_TOPIC = re.compile(r"(?<![A-Za-z0-9_/])/[A-Za-z0-9_][A-Za-z0-9_/]*")
_REF = re.compile(r"(?<![A-Za-z0-9_])([ETL])(\d+)(?![0-9])")
_TID_IN_TEXT = re.compile(r"(?<![A-Za-z0-9_])T(\d+)(?:\s*(?:至|到|～|~|-|—)\s*T(\d+))?(?![0-9])")   # 「T8 至 T16 整段沒有變化」
_FINALLY = re.compile(r"最後|最終|到數據結束|結束時")   # 「中間變過，最後回到開頭的值」說的是錄製結束時
_DESCRIPTOR = re.compile(r"\s?[\u4e00-\u9fff]")      # 值後面直接接中文：「變成 LiDAR 相關任務」是描述，不是值
_PARTICLE = re.compile(r"\s?[且並而後前及與和或的了時]")
# 子句以這些字開頭＝接著前一個子句說（主詞沿用）；以自己的中文主詞開頭的（「各項診斷層級回到初始值」）不沿用
_CONTINUATION = re.compile(r"^\s*(?:最後|最終|之後|此後|中間|且|並|而|同時|都|也|皆|均|再|又|然後|隨後|接著|到數據結束|到最後|直到|後來|仍|一直|"
                           r"沒有|未|無|全程|整段|以上|這些|上述|其值|數值|"
                           r"[A-Za-z](?![A-Za-z0-9_]))")   # 只有述語、沒寫主詞（「…，沒有變化」「以上項目皆沒有變化」）、軸名（「…，w 為 1.0」）也算
_DURING = re.compile(r"中間|期間|其間|之間")   # 「訊息中斷…中間數值沒有變化」：說的是引用的兩個事件之間
_FLAP = 7   # 一個 Key 變化超過這麼多次＝反覆切換（同分析程式 _FLAP_KEEP 的總和）：雜訊，「回到初始」不比
_SENT = re.compile(r"[^。；;！？!?\n]+[。；;！？!?\n]?")
_CLAUSE = re.compile(r"[^，,]+")


def _plus(t):
    return f"+{t:.2f}s"


def _short(v, n=40):
    s = f"{v:.12g}" if isinstance(v, float) else str(v)   # 時間戳這種大數值要看得出差別
    return s if len(s) <= n else s[:n - 1] + "…"


def _norm(v):
    s = str(v).strip().strip("「」『』\"'` ").rstrip(".…").strip()
    try:
        return float(s)
    except ValueError:
        return s.lower()


def _equal(x, y):
    """兩個事實的值一樣嗎（數字照數值比）。"""
    a, b = _norm(x), _norm(y)
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-6 + 1e-3 * abs(b)
    return a == b


def same(claim, actual):
    """模型寫的值跟事實的值一樣嗎：數字照數值比、文字不分大小寫；文字可以只寫開頭；寫了兩個字的，第一個字對上也算
    （「HARD_STOP and」這種接了別的字的寫法）。"""
    words = str(claim).split()
    if "->" in str(actual) and any(same(claim, p) for p in str(actual).split("->") if p):
        return True                            # 路段「2->2」：寫的是端點也算
    for c in [claim] + ([words[0]] if len(words) > 1 else []):
        a, b = _norm(c), _norm(actual)
        if isinstance(a, float) and isinstance(b, float):
            if abs(a - b) <= 1e-6 + 1e-3 * abs(b):
                return True
        elif isinstance(a, str) and isinstance(b, str) and (a == b or (b.startswith(a) and (len(a) >= 3 or b[len(a):len(a) + 1] in (" ", "|")))):
            return True                        # 只寫開頭：3 個字以上，或剛好是一個詞（「R:」對「R: STOP | L: STOP」）
    return False


def _leaves(actual):
    """值是 JSON 字串（amr_base_sw 的 /robot_state、/target_station 這類）時，裡面每一個值。"""
    text = str(actual).strip()
    if text[:1] not in "{[":
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    out = []

    def walk(x):
        if isinstance(x, dict):
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
        elif len(out) < 50:
            out.append(x)
    walk(data)
    return out


def _same_v(claim, actual, aliases):
    """same，再加上訊息定義的常數：值是 0、定義寫 OK=0 → 寫 OK 也算對（aliases：{_norm(值): {小寫的名稱}}）；值是 JSON 字串時，
    寫的是裡面的某一個值也算對（「data=10」對 {"target_station": "10"}）。"""
    if same(claim, actual):
        return True
    names = aliases.get(str(_norm(actual)), ())
    if any(str(_norm(c)) in names for c in [claim] + str(claim).split()[:1]):
        return True
    return any(same(claim, x) for x in _leaves(actual))


def key_match(token, key):
    """句子裡的 Key 對不對得上事實裡的 Key：一樣；只寫了前面的名稱（status.level 對 status.level[sensor_lidar_front]）；只寫了最後
    一段（level 對 status.level）；依名稱展開的項目只寫了最後的欄位（error_code 對 status.values[sensor_lidar_front » error_code]）。"""
    t, k = token.lower(), key.lower()
    if t == k:
        return True
    base, _, idx = k.partition("[")
    idx = idx.rstrip("]")
    if "[" in t:
        tb, _, ti = t.partition("[")
        ti = ti.rstrip("]")
        return (tb == base or base.endswith("." + tb)) and bool(ti) and (idx == ti or idx.endswith(ti))
    if base == t or base.endswith("." + t):
        return True
    return bool(idx) and "»" in idx and idx.rsplit("»", 1)[1].strip() == t


def full_match(token, key):
    """寫的是完整的名稱：一樣、或依名稱展開的項目的欄位名稱（status.level 對 status.level[sensor_lidar_front]）。「沒有變化」「回到初始」
    只認這種——只寫了最後一段（「x、y 軸沒有變化」的 x）會對到不相干的項目（linear_acceleration.x）。"""
    t, k = token.lower(), key.lower()
    return t == k or t == k.partition("[")[0]


def _group(word, key):
    """「winning 項目」：寫的是好幾個 Key 共同的開頭（winning_task、winning_level…）——說的是那幾項，不是整個 Topic。"""
    return key.lower().startswith(word.lower() + "_")


def field_match(token, field):
    """句子裡的名稱是不是這個 Topic 的某個欄位（含上一層：pose 對 pose.pose.position.x）。"""
    t = token.lower()
    return key_match(token, field) or field.lower().startswith(t + ".") or field.lower().startswith(t + "[")


def value_at(v, t):
    """這個 Key 在 t（含 t 那一則訊息）之後的值；t 是 None＝最後的值。變化只留頭尾（count 比 changes 多）、t 落在中間被省略的那段 → None。"""
    if t is None:
        return v.get("last")
    ch = v.get("changes") or []
    if (v.get("count") or 0) > len(ch) and ch and ch[0][0] < t < ch[-1][0]:
        return None
    val = v.get("first")
    for ct, _a, b in ch:
        if ct > t + _EPS:
            break
        val = b
    return val


class _Item:
    """一則說明（或主對話回答的一行）的核對範圍：引用的編號、引用到的 Topic、每個 Topic 引用到的事件時間。"""

    def __init__(self, refs, facts):
        self.facts = facts
        self.rows = {r["id"]: r for r in facts.get("topics") or []}
        self.by_topic = {r["topic"]: r for r in facts.get("topics") or []}
        ev = facts.get("events") or {}
        self.whole = {r for r in refs if r in self.rows}
        self.times = {}
        cited = []
        for r in refs:
            if r in ev:
                tid = ev[r].get("tid")
                self.times.setdefault(tid, []).append(ev[r]["t"])
                cited.append(tid)
            elif r in self.rows:
                cited.append(r)
        self.cited = [self.rows[t] for t in dict.fromkeys(cited) if t in self.rows]
        ts = [t for v in self.times.values() for t in v]
        self.t_item = max(ts) if ts else None
        # 每個 Topic 第一則訊息的時間（開始發布、第一則在中途）：那一刻每個值是「出現」，也算「變成」
        self.first_msg = {}
        for e in ev.values():
            if e.get("kind") in ("start", "first"):
                self.first_msg.setdefault(e.get("tid"), e["t"])

    def aliases(self, row):
        a = getattr(self, "_aliases", None)
        if a is None:
            a = self._aliases = {}
        if row["id"] not in a:
            a[row["id"]] = {str(_norm(v)): {str(_norm(n)) for n in names} for v, names in (row.get("aliases") or {}).items()}
        return a[row["id"]]

    def started_late(self, row):
        """這個 Topic 在錄製中途才開始發布（有開始發布、第一則在中途的事件）：沒有錄製開始時的值。"""
        ev = self.facts.get("events") or {}
        return any(ev.get(e, {}).get("kind") in ("start", "first") for e in row.get("events") or [])

    def named(self, clause):
        """子句裡寫了的 Topic：名稱，或句子裡的 T#（「T8 至 T16 整段沒有變化」「T5、T6 整段沒有變化」）。"""
        out = [self.by_topic[m.group()] for m in _TOPIC.finditer(clause) if m.group() in self.by_topic]
        for m in _TID_IN_TEXT.finditer(clause):
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            out += [self.rows[f"T{i}"] for i in range(a, min(b, a + 60) + 1) if f"T{i}" in self.rows]
        return list({id(r): r for r in out}.values())

    def subjects(self, clause):
        return self.named(clause) or self.cited

    def changes(self, row, key):
        """這一則看得到的這個 Key 的變化：引用了 T#、或只在句子裡寫了 Topic 名稱＝全部；引用了事件＝那幾則訊息的變化。
        Topic 的第一則訊息在錄製中途時，那一則的值算一次「出現」（之前沒有值，None）。"""
        v = row["values"][key]
        ch = list(v.get("changes") or [])
        t0 = self.first_msg.get(row["id"])
        if t0 is not None and not v.get("late"):
            ch = [[t0, None, v.get("first")]] + ch
        times = self.times.get(row["id"])
        if row["id"] in self.whole or not times:
            return ch
        return [c for c in ch if any(abs(c[0] - t) <= _EPS for t in times)]

    def time_of(self, row):
        times = self.times.get(row["id"])
        return max(times) if times else None


def _keys(row, token):
    return [k for k in (row.get("values") or {}) if key_match(token, k)]


def _unverifiable(rows, key):
    """這個名稱在某個主詞的 Topic 裡是核對不了的欄位（文字、陣列、沒有變化的群組）：說的可能是它，不核對（同一句裡兩個 Topic 都有 data）。"""
    return any(field_match(key, f) and not any(key_match(key, k) for k in (r.get("values") or {}))
               for r in rows for f in r.get("fields") or [])


def _transition(item, rows, key, a, b):
    if _unverifiable(rows, key):
        return None
    seen, known = [], False
    for row in rows:
        for k in _keys(row, key):
            if row["values"][k].get("continuous"):
                return None                    # 連續變動的數值：「從 9 增加到 1779」說的是範圍，中間的值不知道，不核對
            known = True
            al = item.aliases(row)
            ch = item.changes(row, k)
            for ct, x, y in ch:
                if _same_v(b, y, al) and (a is None or x is None or _same_v(a, x, al)):   # x 是 None：中途才出現的項目出現的那一刻（之前沒有值）
                    return None
                seen.append((k, ct, x, y))
            if a is not None and len(ch) >= 2 and ch[0][1] is not None and _same_v(a, ch[0][1], al) and _same_v(b, ch[-1][2], al):
                return None                    # 「從 0 增加到 2」：引用的幾次變化合起來（0 → 1 → 2）
    if not known:
        return None
    claim = f"{key} {'從 ' + a + ' ' if a else ''}變成 {b}"
    if seen:
        k, ct, x, y = seen[0]
        was = "（之前沒有這一項）" if x is None else _short(x)
        return f"寫「{claim}」，但引用的事件裡 {k} 是 {was} → {_short(y)}（{_plus(ct)}）"
    return f"寫「{claim}」，但引用的事件裡 {key} 沒有變化"


def _state(item, rows, key, b, end, later=False):
    if _unverifiable(rows, key):
        return None
    bad = None
    for row in rows:
        for k in _keys(row, key):
            v = row["values"][k]
            t = item.time_of(row)
            if end:
                allowed = [v.get("last")]
            elif v.get("continuous"):
                continue                       # 連續變動的數值只知道開頭與最後的值：某一刻的值不核對
            elif t is not None and later:      # 「恢復發布後 linear.x 為 0.0」：從引用的第一個事件起，之後出現過的值都算
                t1 = min(item.times.get(row["id"]) or [t])
                allowed = [value_at(v, t1 - 2 * _EPS), value_at(v, t1)] + [c[2] for c in v.get("changes") or [] if c[0] > t1 + _EPS]
            elif t is not None:
                allowed = [value_at(v, t - 2 * _EPS), value_at(v, t)]
            else:
                allowed = [v.get("first"), v.get("last")] + [c[2] for c in v.get("changes") or []]
            allowed = [x for x in allowed if x is not None]
            if not allowed:
                continue
            if any(_same_v(b, x, item.aliases(row)) for x in allowed):
                return None
            bad = (k, allowed)
    if not bad:
        return None
    k, allowed = bad
    if end:
        return f"寫「{key} 是 {b}」，但到數據結束時 {k}＝{_short(allowed[0])}"
    return f"寫「{key} 是 {b}」，但引用的那一刻 {k} 是 {'／'.join(dict.fromkeys(_short(x) for x in allowed))}"


def _no_change(item, clause, rows, tokens, fields, described=()):
    after = bool(_AFTER.search(clause))
    t0 = item.t_item if after else None
    if after and t0 is None:
        return None
    ts = [t for v in item.times.values() for t in v]
    span = (min(ts), max(ts)) if _DURING.search(clause) and len(ts) >= 2 and max(ts) > min(ts) else None
    if span:                                   # 只看兩個事件之間（開頭與結尾那兩則不算）
        inside = lambda t: span[0] + _EPS < t < span[1] - _EPS   # noqa: E731
    else:
        inside = lambda t: t0 is None or t > t0 + _EPS   # noqa: E731
    ev = item.facts.get("events") or {}
    before_stop = bool(_BEFORE_STOP.search(clause))

    def cut(row):                              # 「在停止發布前沒有變化」：只看那個 Topic 第一次停止或中斷之前
        ts = [ev[e]["t"] for e in row.get("events") or [] if ev.get(e, {}).get("kind") in ("stop", "gap")]
        return min(ts) - _EPS if before_stop and ts else float("inf")
    keyed = [(row, k) for row in rows for tok in tokens for k, v in (row.get("values") or {}).items()
             if full_match(tok, k) and (v.get("count") or 0) <= _FLAP]   # 反覆切換的雜訊（EKF 的計數）不比
    if fields and not keyed:
        return None                            # 寫到的是沒有變化的群組、陣列、只寫了一段的名稱：核對不了，不當成整個 Topic
    if keyed:
        for row, k in keyed:
            v = row["values"][k]
            ch = [c for c in v.get("changes") or [] if inside(c[0]) and c[0] < cut(row)]
            if ch:
                return f"寫「{k} 沒有變化」，但 {k} 在 {_plus(ch[0][0])} 從 {_short(ch[0][1])} 變成 {_short(ch[0][2])}"
            if t0 is None and not span and v.get("continuous"):
                return f"寫「{k} 沒有變化」，但 {k} 的數值有變動（{_short(v.get('first'))} → {_short(v.get('last'))}）"
        return None
    targets = rows                             # 呼叫的地方決定：寫出的 Topic、引用的 T#，或只引用了一個 Topic
    values_only = bool(_VALUE_SCOPE.search(clause)) or before_stop   # 停止之前：說的是值，停止那一則不算
    for row in targets:
        evs = [e for e in row.get("events") or [] if inside(ev.get(e, {}).get("t", 0)) and ev.get(e, {}).get("t", 0) < cut(row)
               and ev.get(e, {}).get("kind") not in described
               and (not values_only or ev.get(e, {}).get("kind") in ("change", "spike"))]
        if evs:
            back = all(_equal(x["last"], x["first"]) for x in row["values"].values() if x.get("varies") and not x.get("late")
                       and not x.get("continuous"))
            return (f"寫「{row['topic']} 沒有變化」，但它{'在那之後' if t0 is not None else ''}有 {len(evs)} 個事件（{'、'.join(evs[:4])}"
                    f"{'…' if len(evs) > 4 else ''}）" + ("；變過又回到開頭的值的，寫「中間變過，最後回到開頭的值」" if back and t0 is None else ""))
        if t0 is None and not span and "數值變動" in (row.get("tags") or []):
            return f"寫「{row['topic']} 沒有變化」，但它的數值有變動（{_short((row.get('ranges') or [''])[0], 60)}）"
    return None


def _back(item, clause, rows, tokens, fields, exclude=((), ())):
    ex_words, ex_topics = exclude
    rows = [r for r in rows if r["topic"] not in ex_topics]
    keyed = {}
    for row in rows:
        for tok in tokens:
            for k in row.get("values") or {}:
                if full_match(tok, k):
                    keyed.setdefault(row["id"], (row, []))[1].append(k)
    if fields and not keyed:
        return None
    restrict = bool(_RESTRICT.search(clause))
    targets = list(keyed.values()) or [(row, list(row.get("values") or {})) for row in rows]
    for row, keys in targets:
        if item.started_late(row):
            continue                           # 錄製中途才開始發布的 Topic 沒有錄製開始時的值：「回到初始」不核對
        t = item.time_of(row)
        if t is None and row["id"] not in item.whole:
            t = item.t_item                    # 只寫了 Topic 名稱：那一則的時間
        if _FINALLY.search(clause):
            t = None                           # 「中間變過，最後回到開頭的值」：說的是錄製結束時
        if restrict and not keyed:             # 「相關數值」「變動過的項目」：只看引用的那一刻變過的項目
            keys = [k for k in keys if item.times.get(row["id"]) and any(abs(c[0] - x) <= _EPS for c in row["values"][k].get("changes") or []
                                                                         for x in item.times[row["id"]])]
        bad = []
        for k in dict.fromkeys(keys):
            v = row["values"][k]
            if v.get("late") or v.get("continuous") or not v.get("varies") or (v.get("count") or 0) > _FLAP:
                continue                       # 中途才出現的沒有錄製開始時的值；連續變動的數值、反覆切換的雜訊不比
            now = value_at(v, t)
            if any(key_match(w, k) or (now is not None and _same_v(w, now, item.aliases(row))) for w in ex_words):
                continue                       # 寫明的例外：寫了這個 Key，或寫了它那時的值（「…，但仍是 HARD_STOP」）
            if now is not None and not _equal(now, v.get("first")):
                bad.append(f"{k}＝{_short(now)}（開頭 {_short(v.get('first'))}）")
        if bad:
            when = f"{_plus(t)} 之後" if t is not None else "到數據結束時"
            return f"寫「{row['topic']} 回到初始」，但 {when} {'、'.join(bad[:2])}{'…' if len(bad) > 2 else ''}"
    return None


def _clause_claims(clause, end):
    """一個子句裡的說法：[(種類, Key, 從, 到)]。同一段文字只算一次（「從 A 變成 B」先認，再認只寫了「變成 B」「是 B」的）。"""
    out, spans = [], []
    for kind, pat in (("change", _FROM_TO), ("change", _ARROW), ("to", _TO_ONLY), ("state", _IS)):
        for m in pat.finditer(clause):
            if any(m.start() < e and s < m.end() for s, e in spans):
                continue
            spans.append((m.start(), m.end()))
            rest = clause[m.end():]
            if _DESCRIPTOR.match(rest) and not _PARTICLE.match(rest):
                continue                       # 「變成 LiDAR 相關任務」：值後面直接接中文，是描述
            if _ALTERNATIVE.match(rest) or len(m.group("key")) < 2 or re.fullmatch(r"[ETLM]\d+", m.group("b")):
                continue                       # 「皆為 0 或空值」：列舉幾種可能；「x、y 為 0」的 x 太短；「維持在 E7 變更後的值」：值是編號
            out.append((kind, m.group("key"), m.groupdict().get("a"), m.group("b"), m.start()))
    return out


def problems(text, refs, facts, limit=3):
    """一段文字（一則說明或重點、主對話回答的一行）跟事實對不上的說法 → 問題清單（每一條寫寫了什麼、事實是什麼）。
    refs：這段文字引用的編號（E#、T#、L#）；facts 沒有 values（第十一輪以前的 job）時不核對。"""
    if not any(r.get("values") for r in facts.get("topics") or []):
        return []
    text = str(text or "").replace("`", "").replace("**", "")
    item = _Item(list(dict.fromkeys(list(refs or []) + refs_in(text))), facts)   # 句子裡寫的編號（「E50 之後…」）也算引用
    out = []
    sents = _SENT.findall(text)
    for i, sent in enumerate(sents):
        sent = _MID_EXCEPT.sub("，", sent)
        m_end = _END.search(sent)              # 「到最後」「數據結束時」只管寫在它後面的說法（「恢復發布，此時 linear.x 為 0.35，…，到最後變成 0.1」）
        end_at = m_end.start() if m_end else None
        end = end_at is not None
        partial = bool(_PARTIAL.search(sent))   # 「其餘項目皆為 0.0，且沒有變化」：「其餘」在前一個子句，說的還是那些項目
        described = {k for pat, kinds in _DESCRIBED if pat.search(sent) for k in kinds}
        # 寫明的例外（同一句、或下一句開頭的「但…」）：寫到的 Key、Topic、值不算進「回到初始」；「沒有變化」那一句不核對
        nxt = _CLAUSE.findall(sents[i + 1])[:1] if i + 1 < len(sents) else []
        ex = [c for c in _CLAUSE.findall(sent) + nxt if _EXCEPT.match(c)]
        exclude = ([m.group() for c in ex for m in re.finditer(_VAL, c)], {m.group() for c in ex for m in _TOPIC.finditer(c)})
        prev = ([], [], [])
        for cm in _CLAUSE.finditer(sent):
            clause = cm.group()
            if _HEDGE.search(clause):
                continue
            named = item.named(clause)
            rows = named or item.cited
            if not rows:
                continue
            words = [m.group("key") for m in re.finditer(_KEY, clause) if len(m.group("key")) > 1]   # 「x、y 軸」的 x 不當名稱
            tokens = [w for w in words if any(_keys(r, w) for r in rows)]
            fields = [w for w in words if any(field_match(w, f) for r in rows for f in r.get("fields") or [])]
            # 「/system/safety_command 的 winning 項目回到初始值」：寫的是一組 Key 的共同開頭——說的是那幾項，不是整個 Topic
            tokens += list(dict.fromkeys(k for w in words if w not in tokens and w not in fields for r in rows
                                         for k in r.get("values") or {} if _group(w, k)))
            if not fields and not named and _CONTINUATION.match(clause):   # 接著前一個子句說：沿用主詞（「stop_reasons 中間變過，最後回到開頭的值」）
                if not tokens:
                    tokens, fields, named = prev
                elif prev[2] and all(any(_keys(r, w) for r in prev[2]) for w in tokens):
                    named = prev[2]            # 自己寫了 Key（「…，且 active_error_tasks 沒有變化」）：Key 用自己的，Topic 沿用
                rows = named or rows
            prev = (tokens, fields, named)
            # 沒有寫出 Topic 時，「沒有變化」「回到初始」說的是哪個 Topic：引用的 T#（整個 Topic），或只引用了一個 Topic；一刻裡好幾個 Topic 的
            # 事件（「各項診斷層級回到初始值」）說的可能只是其中幾個——不核對
            whole_rows = named or [r for r in item.cited if r["id"] in item.whole] or (item.cited if len(item.cited) == 1 else [])
            found = []
            named_at = [(m.start(), item.by_topic[m.group()]) for m in _TOPIC.finditer(clause) if m.group() in item.by_topic]
            for kind, key, a, b, at in _clause_claims(clause, end):
                at_end = end_at is not None and cm.start() + at >= end_at
                later = bool(_LATER.search(sent[:cm.start() + at]))

                def check(subj):
                    if kind == "change" or (kind == "to" and not at_end):
                        return _transition(item, subj, key, a, b)
                    return _state(item, subj, key, b, at_end, later=later)   # 「是 X」；到數據結束的「回到 X」＝最後的值
                before = [r for p, r in named_at if p < at]
                got = check(before[-1:] or rows)   # 一句寫了好幾個 Topic：主詞是前面最近的那個（「/a 的 data=10、/b 的 data=MOVING」）
                if got and len(before) > 1 and check(before) is None:
                    got = None                 # 「/route_status 與 /bt_active_node 第一則訊息（data=DONE、NotifyDone）」：並列的主詞，有一個對得上就不擋
                found.append(got)
            if not partial and (whole_rows or tokens or fields):
                own_ex = bool(_EXCEPT.match(clause))   # 例外那個子句自己的說法照常核對
                nc = _NO_CHANGE.search(clause)
                if nc and (own_ex or not ex) and not _ALTERNATIVE.match(clause[nc.end():]):   # 「整段沒有變化或沒有訊息」：列舉
                    subj = (whole_rows if not (tokens or fields) else rows, tokens, fields)
                    preds = list(_PRED.finditer(clause, 0, nc.start()))
                    if preds:                  # 「/a 的 data 為 FAIL、/T16、/T17 整段沒有變化」：說的是最後一個「為 X」後面列的
                        seg = clause[preds[-1].end():nc.start()]
                        seg_words = {m.group("key") for m in re.finditer(_KEY, seg)}
                        s_named, s_tokens = item.named(seg), [w for w in tokens if w in seg_words]
                        s_fields = [w for w in fields if w in seg_words]
                        if s_named or s_tokens or s_fields:
                            subj = (s_named if not (s_tokens or s_fields) else (s_named or rows), s_tokens, s_fields)
                    found.append(_no_change(item, clause, *subj, described=described))
                if any(not _NOT_BACK.search(clause[:m.start()]) and not _BACK_ALT.match(clause[m.end():])
                       for m in _BACK.finditer(clause)):   # 「沒有回到初始」「回到初始值或變更」不算
                    found.append(_back(item, clause, whole_rows if not (tokens or fields) else rows, tokens, fields,
                                       ((), set()) if own_ex else exclude))
            out += [p for p in found if p and p not in out]
    return out[:limit]


def refs_in(text):
    """一段文字裡寫到的編號（主對話的回答：「…（E6）」「（E2, E3）」）。"""
    return list(dict.fromkeys(f"{m.group(1)}{int(m.group(2))}" for m in _REF.finditer(str(text or ""))))


def reply_problems(reply, facts, limit=3):
    """主對話依數據分析的報告回答：一行一行核對（每一行用它自己寫到的編號；沒寫編號的看句子裡寫的 Topic 名稱）。"""
    out = []
    for line in str(reply or "").splitlines():
        if not line.strip():
            continue
        for p in problems(line, refs_in(line), facts, limit):
            if p not in out:
                out.append(p)
    return out[:limit]
