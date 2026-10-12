"""C／C++ 的共用層：repo_map、code_refs、code_check、code_test、寫入技能的語法把關、規劃的名稱索引共用。

不是完整的 C++ parser，是只用標準庫的輕量掃描器——看不懂的寫法寧可少列，不要列錯：
- strip_code：把註解、字串與字元常數的內容換成空白（長度與換行位置不變），後面的掃描不會被註解或字串裡的括號、名稱誤導。
- balance_check：()[]{} 與 #if／#endif 配對。抓「輸出被截斷」「少一個 }」這種整個檔案都編譯不過的錯；寫入技能用它把關
  （不呼叫編譯器：跨檔的錯誤要等 code_check／code_test 編譯時才看得到）。
- scan：namespace／class／struct／enum／函式與方法（定義或宣告）、typedef、巨集 → 結構大綱、名稱索引、code_refs 的分類。
- 建置與測試：偵測 CMake（有沒有註冊測試）、有 test／check 目標的 Makefile、C／C++ 測試原始檔；推測編譯參數
  （有 compile_commands.json 就照它）；整理 gcc 的錯誤訊息、gtest 的失敗細節、ctest 的結果。
- 一個工作區裡有好幾個專案（ROS 2 的 colcon 工作區）：每個檔案依所屬的套件（package.xml、有 project() 的 CMakeLists.txt）
  決定 include 目錄與依賴；找不到的標頭是宣告過的外部依賴（這台主機沒裝的 rclcpp 之類）時，分得出來不是程式的錯。
"""
import json
import os
import re
import shlex
import sys
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc

C_SOURCE_EXTS = {".c"}
CPP_SOURCE_EXTS = {".cpp", ".cc", ".cxx", ".c++"}
SOURCE_EXTS = C_SOURCE_EXTS | CPP_SOURCE_EXTS
HEADER_EXTS = {".h", ".hpp", ".hh", ".hxx", ".h++", ".inl", ".ipp", ".tpp"}
ALL_EXTS = SOURCE_EXTS | HEADER_EXTS


def ext_of(path):
    return os.path.splitext(path)[1].lower()


def is_c_family(path):
    return ext_of(path) in ALL_EXTS


# ---------------------------------------------------------------- 去掉註解與字串
_RAW_PREFIXES = ("u8R", "uR", "UR", "LR", "R")


def _raw_string_end(text, i):
    """text[i] 是「"」，前面是 R／u8R／LR… 時是 raw string：回傳結尾（最後一個「"」之後的位置）；不是回 None。"""
    for p in _RAW_PREFIXES:
        a = i - len(p)
        if a >= 0 and text[a:i] == p and (a == 0 or not (text[a - 1].isalnum() or text[a - 1] == "_")):
            paren = text.find("(", i + 1, i + 18)
            if paren < 0:
                return None
            delim = text[i + 1:paren]
            if any(ch in delim for ch in ' \\)\n\t"'):
                return None
            end = text.find(")" + delim + '"', paren + 1)
            return len(text) if end < 0 else end + len(delim) + 2
    return None


def _blank_preprocessor(s):
    """前置處理指令（# 開頭的行與它的 \\ 續行）換成空白：#define 裡不成對的括號不算。"""
    lines = s.split("\n")
    cont = False
    for idx, ln in enumerate(lines):
        if cont or ln.lstrip().startswith("#"):
            cont = ln.rstrip().endswith("\\")
            lines[idx] = " " * len(ln)
        else:
            cont = False
    return "\n".join(lines)


def _strip(text, blank_preprocessor=False, keep_strings=False):
    """回傳 (註解、字串與字元常數的內容換成空白的文字, 問題 list[(行號, 說明)])；長度與換行位置跟原文一樣。
    keep_strings：字串與字元常數保留原文（只去掉註解；給大綱顯示預設參數用）。"""
    out = list(text)
    n = len(text)
    problems = []

    def blank(a, b, literal=False):
        if literal and keep_strings:
            return
        for k in range(max(0, a), min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    def line_at(pos):
        return text.count("\n", 0, pos) + 1

    i = 0
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] in "/*":
            if text[i + 1] == "/":
                j = text.find("\n", i)
                j = n if j < 0 else j
                blank(i, j)
                i = j
                continue
            j = text.find("*/", i + 2)
            if j < 0:
                problems.append((line_at(i), "註解「/*」到檔案結尾都沒有結束（少了「*/」）"))
                blank(i, n)
                break
            blank(i, j + 2)
            i = j + 2
            continue
        if c == '"':
            raw_end = _raw_string_end(text, i)
            if raw_end:
                blank(i + 1, raw_end - 1, True)
                i = raw_end
                continue
            j = i + 1
            while j < n and text[j] not in '"\n':
                j += 2 if text[j] == "\\" else 1
            if j >= n or text[j] == "\n":
                problems.append((line_at(i), "字串沒有結束（少了右邊的「\"」）"))
                blank(i + 1, j, True)
                i = j
                continue
            blank(i + 1, j, True)
            i = j + 1
            continue
        if c == "'":
            k = i - 1
            while k >= 0 and (text[k].isalnum() or text[k] in "_'"):
                k -= 1
            if text[k + 1:i][:1].isdigit():        # 數字分隔符號：1'000'000
                i += 1
                continue
            j = i + 1
            while j < n and j - i <= 12 and text[j] not in "'\n":
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == "'":
                blank(i + 1, j, True)
                i = j + 1
                continue
            i += 1                                  # 不是字元常數（例如 #error 裡的 don't）
            continue
        i += 1
    s = "".join(out)
    return (_blank_preprocessor(s) if blank_preprocessor else s), problems


def strip_code(text, blank_preprocessor=False):
    return _strip(text, blank_preprocessor)[0]


# ---------------------------------------------------------------- 括號配對（寫入技能的把關）
_CLOSE_OF = {"(": ")", "[": "]", "{": "}"}
_OPEN_OF = {")": "(", "]": "[", "}": "{"}
_PP_IF_RE = re.compile(r"^[ \t]*#[ \t]*(if|ifdef|ifndef|endif)\b", re.M)


def balance_check(text):
    """C／C++ 的 ()[]{} 與 #if／#endif 配對（忽略註解、字串、前置處理指令裡的括號）：回傳 (ok, 訊息)。"""
    s, problems = _strip(text, blank_preprocessor=True)
    if problems:
        ln, msg = problems[0]
        return False, f"第 {ln} 行：{msg}"
    stack, line = [], 1
    for ch in s:
        if ch == "\n":
            line += 1
        elif ch in "([{":
            stack.append((ch, line))
        elif ch in ")]}":
            if not stack:
                return False, f"第 {line} 行多了一個「{ch}」（前面沒有對應的「{_OPEN_OF[ch]}」）"
            top, tl = stack.pop()
            if top != _OPEN_OF[ch]:
                return False, (f"第 {line} 行的「{ch}」跟第 {tl} 行的「{top}」對不起來"
                               f"（中間少了「{_CLOSE_OF[top]}」或多了「{ch}」）")
    if stack:
        top, tl = stack[-1]
        more = f"，總共有 {len(stack)} 個括號沒有關閉" if len(stack) > 1 else ""
        return False, (f"第 {tl} 行的「{top}」到檔案結尾都沒有對應的「{_CLOSE_OF[top]}」{more}"
                       f"（檔案是不是被截斷、或結尾少寫了？）")
    kinds = [m.group(1) for m in _PP_IF_RE.finditer(strip_code(text))]
    opens = sum(1 for k in kinds if k != "endif")
    if opens != len(kinds) - opens:
        return False, f"#if／#ifdef／#ifndef 有 {opens} 個，#endif 有 {len(kinds) - opens} 個，沒有配對（include guard 少了結尾的 #endif？）"
    return True, ""


# ---------------------------------------------------------------- 結構掃描
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|::|->|\.\.\.|&&|\S")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*$")
_NOT_NAMES = {
    "if", "for", "while", "switch", "return", "sizeof", "catch", "do", "else", "case", "new", "delete", "throw",
    "decltype", "alignof", "alignas", "static_assert", "typeid", "co_return", "co_await", "co_yield", "using", "typedef",
    "template", "noexcept", "__attribute__", "__declspec", "defined", "requires", "int", "char", "void", "double", "float",
    "long", "short", "unsigned", "signed", "bool", "auto", "const", "volatile", "static", "inline", "virtual", "explicit",
    "constexpr", "extern", "struct", "class", "union", "enum", "namespace", "typename", "and", "or", "not", "goto",
}
_TYPE_WORDS = {"int", "char", "void", "double", "float", "long", "short", "unsigned", "signed", "bool", "auto", "const",
               "volatile", "struct", "class", "enum", "union", "typename", "size_t", "string", "std"}
_SPEC_WORDS = {"virtual", "static", "inline", "explicit", "constexpr", "consteval", "extern", "friend", "typename",
               "mutable", "__inline", "__forceinline"}
TEST_MACROS = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST", "TYPED_TEST_P", "TEST_CASE", "SCENARIO", "BOOST_AUTO_TEST_CASE",
               "BOOST_FIXTURE_TEST_CASE"}
_ACCESS_RE = re.compile(r"\b(?:public|private|protected|signals|slots|Q_SIGNALS|Q_SLOTS)\s*:(?!:)")
# 巨集名稱的分支前後要有 \b：沒有的話，一串大寫的名稱（GMOCK_MAYBE_5046_）可以被外層的 * 切成任意多段，後面一對不上就把每一種切法
# 都試一遍（指數時間）。實測（SWE-bench 評測，2026-10-09）：fmt 內附的 gmock.h、redis 的 jemalloc 標頭、nlohmann/json 的 doctest.h、
# astropy 的 expat.h 讓 repo_map 卡住 10 分鐘（腳本的逾時）、規劃時建符號索引時卡到 job 逾時；加 \b 之後 gmock.h（1.1 萬行）0.09 秒。
_POST_RE = re.compile(
    r"(?:\s*(?:const|volatile|noexcept(?:\s*\([^()]*\))?|override|final|&&|&|throw\s*\([^()]*\)|try|"
    r"->\s*[\w:<>,\s*&\[\]]+?|=\s*(?:0|default|delete)|__attribute__\s*\(\([^()]*\)\)|\b[A-Z_][A-Z0-9_]*\b))*"
    r"\s*(?::(?!:).*)?")
_OPERATOR_RE = re.compile(
    r"((?:[A-Za-z_]\w*(?:\s*<[^<>]*>)?\s*::\s*)*operator\s*(?:\(\s*\)|\[\s*\]|new(?:\s*\[\s*\])?|delete(?:\s*\[\s*\])?|"
    r"\"\"\s*\w+|[^\w\s(]+|[A-Za-z_][\w\s:<>*&]*?))\s*\(")


def _strip_template(h):
    """去掉開頭的 template<…>（可能好幾層）。"""
    while h.startswith("template"):
        j = h.find("<")
        if j < 0:
            break
        depth, k = 0, j
        while k < len(h):
            if h[k] == "<":
                depth += 1
            elif h[k] == ">":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if k >= len(h):
            break
        h = h[k + 1:].strip()
    return h


def _clean_header(hdr):
    """宣告或定義的開頭（上一個 ; { } 之後到這裡）→ (整理過的文字, 第一個有意義的字元在 hdr 裡的位置)。"""
    m = re.match(r"\s*(?:(?:public|private|protected|signals|slots|Q_SIGNALS|Q_SLOTS)\s*:(?!:)\s*)*", hdr)
    off = m.end()
    h = _ACCESS_RE.sub(" ", " ".join(hdr[off:].split())).strip()
    h = _strip_template(h)
    h = re.sub(r"^(?:\[\[.*?\]\]\s*)+", "", h)
    return h, off


def _matching(h, open_pos, o="(", c=")"):
    depth = 0
    for k in range(open_pos, len(h)):
        if h[k] == o:
            depth += 1
        elif h[k] == c:
            depth -= 1
            if depth == 0:
                return k
    return None


def _qualified_name_start(toks, j):
    """toks[j] 是名稱的最後一段：往前接上 ~、A::、A<T>:: → 回傳名稱開頭的 token 索引。"""
    k = j
    if k - 1 >= 0 and toks[k - 1].group() == "~":
        k -= 1
    while k - 2 >= 0 and toks[k - 1].group() == "::":
        p = k - 2
        if toks[p].group() == ">":
            depth, q = 0, p
            while q >= 0:
                g = toks[q].group()
                depth += 1 if g == ">" else (-1 if g == "<" else 0)
                if depth == 0:
                    break
                q -= 1
            p = q - 1
        if p >= 0 and _IDENT_RE.match(toks[p].group()):
            k = p
        else:
            break
    return k


def parse_signature(h):
    """宣告或定義的開頭（整理過）→ {"ret", "name", "params", "post"}；不是函式回 None。"""
    m = _OPERATOR_RE.search(h)
    if m:
        open_pos = m.end() - 1
        close = _matching(h, open_pos)
        if close is None:
            return None
        post = h[close + 1:].strip()
        if not _POST_RE.fullmatch(post):
            return None
        return {"ret": h[:m.start(1)].strip(), "name": re.sub(r"\s+", "", m.group(1)).replace("operator", "operator "),
                "params": h[open_pos + 1:close].strip(), "post": post}
    toks = list(_TOKEN_RE.finditer(h))
    paren = angle = 0
    for idx, t in enumerate(toks):
        v = t.group()
        if v == "(":
            prev = toks[idx - 1].group() if idx else ""
            if paren == 0 and angle == 0 and _IDENT_RE.match(prev) and prev not in _NOT_NAMES:
                close = _matching(h, t.start())
                if close is None:
                    return None
                post = h[close + 1:].strip()
                if not _POST_RE.fullmatch(post):
                    return None
                k = _qualified_name_start(toks, idx - 1)
                return {"ret": h[:toks[k].start()].strip(), "name": re.sub(r"\s+", "", h[toks[k].start():toks[idx - 1].end()]),
                        "params": h[t.end():close].strip(), "post": post}
            paren += 1
        elif v == ")":
            paren -= 1
        elif v == "<" and paren == 0 and idx and _IDENT_RE.match(toks[idx - 1].group()):
            angle += 1
        elif v == ">" and paren == 0 and angle > 0:
            angle -= 1
    return None


def _split_top(text, sep=","):
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _looks_like_params(p):
    """括號裡是不是參數宣告（用來排除 std::vector<int> v(10); 這種變數宣告）。"""
    p = p.strip()
    if not p or p in ("void", "..."):
        return True
    for piece in _split_top(p):
        piece = piece.split("=")[0].strip()
        if piece == "...":
            continue
        if not piece or re.match(r"^[\d\"'+\-.]", piece):
            return False
        words = re.findall(r"[A-Za-z_]\w*", piece)
        if len(words) >= 2 or re.search(r"[*&<:\[]", piece) or (words and words[0] in _TYPE_WORDS):
            continue
        return False
    return True


def _short(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _class_name(rest):
    rest = re.sub(r"\[\[.*?\]\]|\b(?:alignas|__attribute__|__declspec)\s*\((?:[^()]|\([^()]*\))*\)", " ", rest)
    m = re.search(r"(?<!:):(?!:)", rest)
    head, bases = (rest[:m.start()], rest[m.end():]) if m else (rest, "")
    words = [w for w in re.findall(r"[A-Za-z_][\w:]*(?:<[^{]*>)?", head) if w != "final"]
    return (words[-1] if words else ""), " ".join(bases.split())


def _classify(h):
    """{ 前面的開頭 → (種類, 資訊)。種類：namespace、extern、class／struct／union、enum、function、other。"""
    if not h:
        return "other", None
    m = re.fullmatch(r"(?:inline\s+)?namespace\b\s*([\w:]*)", h)
    if m:
        return "namespace", {"name": m.group(1)}
    if re.fullmatch(r'extern\s*"[^"]*"', h):
        return "extern", None
    m = re.match(r"^(typedef\s+)?(class|struct|union)\b(.*)$", h)
    if m and ("(" not in m.group(3) or re.search(r"\b(alignas|__attribute__|__declspec)\s*\(", m.group(3))) \
            and "=" not in m.group(3):
        name, bases = _class_name(m.group(3))
        return m.group(2), {"name": name, "bases": bases, "typedef": bool(m.group(1))}
    m = re.match(r"^(typedef\s+)?enum\b(?:\s+(?:class|struct)\b)?\s*([A-Za-z_]\w*)?", h)
    if m and "(" not in h:
        return "enum", {"name": m.group(2) or "", "typedef": bool(m.group(1))}
    sig = parse_signature(h)
    if sig and sig["name"].split("::")[-1] not in _NOT_NAMES:
        return "function", sig
    return "other", None


def _brace_pairs(s):
    pairs, stack = {}, []
    for i, ch in enumerate(s):
        if ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            pairs[stack.pop()] = i
    for i in stack:
        pairs[i] = len(s) - 1
    return pairs


def _func_label(sig, decl):
    ret = " ".join(w for w in sig["ret"].split() if w not in ("inline", "extern"))
    post = re.sub(r"(?<!:):(?!:).*$", "", sig["post"]).strip()     # 建構子的初始化串列不列
    name = sig["name"]
    if name in TEST_MACROS:
        return f"{name}({_short(sig['params'], 70)})"
    text = f"{ret + ' ' if ret else ''}{name}({_short(sig['params'], 60)}){' ' + post if post else ''}{';' if decl else ''}"
    return _short(text, 110)


class _Scanner:
    def __init__(self, text):
        self.text = text
        self.s, _ = _strip(text, blank_preprocessor=True)
        self.cs, _ = _strip(text, blank_preprocessor=True, keep_strings=True)   # 只去註解：標籤裡的預設參數照原文顯示
        self.starts = [0] + [m.end() for m in re.finditer("\n", self.s)]
        self.pairs = _brace_pairs(self.s)
        self.out = []

    def line(self, pos):
        return bisect_right(self.starts, pos)

    def add(self, kind, name, label, a, b, depth, cls=None, decl=False, hdr_end=None, params=None):
        self.out.append({"kind": kind, "name": name, "label": label, "line": self.line(a), "end": self.line(b),
                         "hdr_end": self.line(hdr_end if hdr_end is not None else a), "depth": depth, "cls": cls,
                         "decl": decl, "params": params})
        return self.out[-1]

    def label_sig(self, sig, a, b):
        """同一段開頭用保留字串的版本再解析一次：名稱一樣就用它（預設參數的字串照原文），不一樣（字串裡有括號之類）用原本的。"""
        raw = parse_signature(_clean_header(self.cs[a:b])[0])
        return raw if raw and raw["name"] == sig["name"] else sig

    def declaration(self, hdr, hstart, end_pos, cls, depth):
        """以 ; 結尾的敘述：函式宣告（原型）、方法宣告、typedef／using 別名。"""
        h, off = _clean_header(hdr)
        if not h:
            return
        a = hstart + off
        m = re.match(r"^using\s+([A-Za-z_]\w*)\s*=", h)
        if m:
            self.add("typedef", m.group(1), f"using {m.group(1)} = …", a, end_pos, depth, cls)
            return
        if h.startswith("typedef"):
            m = re.search(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", h) or re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*$", h)
            if m:
                self.add("typedef", m.group(1), _short(h, 90) + ";", a, end_pos, depth, cls)
            return
        if "(" not in h or h.startswith(("friend class", "friend struct", "static_assert", "return")):
            return
        sig = parse_signature(h)
        if not sig or sig["name"].split("::")[-1] in _NOT_NAMES:
            return
        if cls is None:
            if not _looks_like_params(sig["params"]) or re.fullmatch(r"[A-Z_][A-Z0-9_]*", sig["name"]):
                return                      # 變數宣告（最惱人的解析）或巨集呼叫（INSTANTIATE_TEST_SUITE_P(...);）
        owner = cls or (sig["name"].rsplit("::", 1)[0] if "::" in sig["name"] else None)
        full = self.label_sig(sig, hstart, end_pos)
        self.add("decl", sig["name"], _func_label(full, True), a, end_pos, depth, owner, decl=True, hdr_end=end_pos,
                 params=full["params"])

    def block(self, a, b, cls, depth):
        s, i, hstart, pending = self.s, a, a, None
        while i < b:
            c = s[i]
            if c == ";":
                hdr = s[hstart:i]
                if pending is not None and hdr.strip():
                    m = re.search(r"([A-Za-z_]\w*)\s*$", hdr)
                    if m and not pending["name"]:
                        pending["name"] = m.group(1)
                        pending["label"] = pending["label"].replace("（匿名）", m.group(1), 1)
                else:
                    self.declaration(hdr, hstart, i, cls, depth)
                pending = None
                hstart = i + 1
            elif c == "{":
                close = self.pairs.get(i, b)
                hdr = s[hstart:i]
                h, off = _clean_header(hdr)
                if re.search(r"\)\s*(?:noexcept\s*)?:(?!:)[^;]*[\w>]\s*$", h):
                    i = close + 1           # 建構子初始化串列裡的 x_{…}：還是開頭的一部分
                    continue
                start = hstart + off
                kind, info = _classify(h)
                if kind == "namespace":
                    name = info["name"]
                    self.add("namespace", name, f"namespace {name or '（匿名）'}", start, close, depth, hdr_end=i)
                    self.block(i + 1, close, None, depth)
                elif kind == "extern":
                    self.block(i + 1, close, cls, depth)
                elif kind in ("class", "struct", "union"):
                    name = info["name"]
                    full = f"{cls}::{name}" if cls and name else name
                    label = f"{kind} {name or '（匿名）'}" + (f" : {_short(info['bases'], 60)}" if info["bases"] else "")
                    e = self.add(kind, full, label, start, close, depth, cls, hdr_end=i)
                    self.block(i + 1, close, full or cls, depth + 1)
                    pending = e if (info["typedef"] or not name) else None
                elif kind == "enum":
                    name = info["name"]
                    e = self.add("enum", name, f"enum {name or '（匿名）'}", start, close, depth, cls, hdr_end=i)
                    pending = e if (info["typedef"] or not name) else None
                elif kind == "function":
                    name = info["name"]
                    owner = cls or (name.rsplit("::", 1)[0] if "::" in name else None)
                    k = "test" if name in TEST_MACROS else "function"
                    full = self.label_sig(info, hstart, i)
                    self.add(k, name, _func_label(full, False), start, close, depth, owner, hdr_end=i, params=full["params"])
                i = close + 1
                hstart = i
                if kind not in ("class", "struct", "union", "enum"):
                    pending = None
                continue
            i += 1


def scan(text):
    """C／C++ 檔案的結構 → list of dict：kind（namespace／class／struct／union／enum／function／test／decl／typedef／macro）、
    name（類別裡的方法是 類別::名稱）、label（大綱顯示的文字）、line／end（行號範圍）、hdr_end（開頭的最後一行）、depth、cls、decl。"""
    sc = _Scanner(text)
    sc.block(0, len(sc.s), None, 0)
    plain = strip_code(text)
    for m in re.finditer(r"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_]\w*)(\()?", plain, re.M):
        ln = sc.line(m.start(1))
        sc.out.append({"kind": "macro", "name": m.group(1), "label": f"#define {m.group(1)}{'(…)' if m.group(2) else ''}",
                       "line": ln, "end": ln, "hdr_end": ln, "depth": 0, "cls": None, "decl": False})
    sc.out.sort(key=lambda e: (e["line"], e["depth"]))
    return sc.out


_GUARD_RE = re.compile(r"^[A-Z0-9_]*_(H|HPP|HH|HXX|H_|HPP_|INCLUDED)_*$")


def outline(text, max_items=60):
    """repo_map／worker 用的大綱：[(層級, 文字)]。namespace 裡的東西不加縮排（類別裡的成員才加），include guard 的巨集不列。"""
    items = []
    for e in scan(text):
        if e["kind"] == "macro" and _GUARD_RE.match(e["name"]):
            continue
        rng = f"L{e['line']}" if e["decl"] or e["kind"] in ("macro", "typedef") or e["line"] == e["end"] \
            else f"L{e['line']}-{e['end']}"
        items.append((e["depth"], f"{e['label']} {rng}"))
        if len(items) >= max_items:
            items.append((0, f"…（宣告太多，只列前 {max_items} 個；用 code_view 或 code_search 看細節）"))
            break
    return items


def owner_name(cls):
    """類別的簡短名稱：ns::Outer::Inner → Inner、Stack<T> → Stack。"""
    return re.sub(r"<.*>$", "", (cls or "").split("::")[-1]).strip()


def definitions(text):
    """名稱索引用：[(名稱, 種類, 行號)]。方法的鍵是 類別.方法；種類：class、type、def（函式本體）、method（方法本體）、
    decl（只有宣告：標頭的原型、類別裡的方法宣告）——呼叫端有本體的定義時就不用宣告。"""
    out = []
    for e in scan(text):
        if e["kind"] in ("namespace", "macro", "test") or not e["name"]:
            continue
        name = e["name"]
        last = name.split("::")[-1]
        if e["kind"] in ("class", "struct", "union", "enum", "typedef"):
            out.append((last, "class" if e["kind"] != "typedef" else "type", e["line"]))
            continue
        owner = owner_name(e["cls"])
        kind = "decl" if e["decl"] else ("method" if owner else "def")
        out.append((f"{owner}.{last}" if owner else last, kind, e["line"]))
    return out


def refs(text, name, cls=None):
    """C／C++ 檔裡某個名稱的出現處（註解與字串裡的不算）→ {"def": [(行號, 說明)], "decl": [...], "use": [...]}。"""
    word = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
    s = strip_code(text)
    found = {"def": [], "decl": [], "use": []}
    if not word.search(s):
        return found
    defs, decls = {}, {}
    kinds = {"class": "class", "struct": "struct", "union": "union", "enum": "enum", "typedef": "typedef", "macro": "#define",
             "function": "函式定義", "decl": "宣告"}
    for e in scan(text):
        last = e["name"].split("::")[-1]
        if last != name:
            continue
        owner = owner_name(e["cls"])
        if cls and owner != cls and e["kind"] not in ("class", "struct", "union"):
            continue
        why = kinds.get(e["kind"], e["kind"])
        if owner and e["kind"] in ("function", "decl"):
            why = f"{'方法定義' if e['kind'] == 'function' else '方法宣告'} in {owner}"
        target = decls if e["decl"] else defs
        for ln in range(e["line"], e["hdr_end"] + 1):
            target.setdefault(ln, why)
    for i, ln in enumerate(s.split("\n"), 1):
        if not word.search(ln):
            continue
        if i in defs:
            found["def"].append((i, defs[i]))
        elif i in decls:
            found["decl"].append((i, decls[i]))
        else:
            found["use"].append((i, "使用"))
    return found


# ---------------------------------------------------------------- 建置系統與測試
_TEST_NAME_RE = re.compile(r"^(test_.*|.*_tests?|tests?|.*_unittest|unit_?tests?|.*_spec)\.(c|cc|cpp|cxx|c\+\+)$", re.I)
_TEST_DIR_NAMES = {"test", "tests", "unit_tests", "unittests", "unit_test", "unittest", "gtest", "gtests", "testing"}
_MAKEFILE_NAMES = ("GNUmakefile", "makefile", "Makefile")
_TEST_MAKEFILE_RE = re.compile(r"^(?:makefile|Makefile|GNUmakefile)[._-]?tests?$|^tests?\.mk$|^Makefile\.(?:test|check)$", re.I)
_CMAKE_TEST_RE = re.compile(r"\b(add_test|gtest_discover_tests|gtest_add_tests|catch_discover_tests|doctest_discover_tests)\s*\(", re.I)


def is_test_source(rel):
    """C／C++ 的測試原始檔：檔名像 test_x.cpp、x_test.cpp、x_tests.cc，或放在 tests／test／unit_tests 目錄裡。"""
    base = os.path.basename(rel)
    if ext_of(base) not in SOURCE_EXTS:
        return False
    if _TEST_NAME_RE.match(base):
        return True
    return any(p.lower() in _TEST_DIR_NAMES for p in rel.replace("\\", "/").split("/")[:-1])


def make_targets(text):
    return set(re.findall(r"^([A-Za-z0-9_.\-]+)\s*:(?!=)", text, re.M))


def has_main(text):
    return bool(re.search(r"\b(?:int|void)\s+main\s*\(", strip_code(text, blank_preprocessor=True)))


def uses_gtest(text):
    return bool(re.search(r"#\s*include\s*[<\"](gtest|gmock)/", text))


def gtest_suites(text):
    """測試檔裡 TEST(Suite, Name)／TEST_F(…) 的 Suite 名稱（依出現順序、不重複）。"""
    s = strip_code(text, blank_preprocessor=True)
    return list(dict.fromkeys(re.findall(r"\b(?:TEST|TEST_F|TEST_P|TYPED_TEST|TYPED_TEST_P)\s*\(\s*([A-Za-z_]\w*)\s*,", s)))


def detect(root, base=""):
    """工作區的 C／C++ 資訊：sources（非測試的 .c／.cpp）、headers、tests（測試原始檔）、cmake（None 或 {"tests": 有沒有註冊測試}）、
    make（None 或 (makefile 檔名, 目標)）、lang（"C++"／"C"／None）、std（例如 c++17）、deps（宣告的外部依賴，見 declared_deps）、
    ros（ROS 套件的 build_type，例如 ament_cmake；不是 ROS 套件為 None）、base。檔名都是相對 root 的路徑。
    base：只看 root 底下的這個子專案（例如 colcon 工作區的 src/my_pkg，見 project_dir），檔名仍然相對於 root。"""
    if base:
        info = detect(os.path.join(root, base))
        for key in ("sources", "headers", "tests"):
            info[key] = [os.path.join(base, f) for f in info[key]]
        info["base"] = base
        return info
    files = [rel for _, rel in cc.iter_files(root, exts=ALL_EXTS)]
    info = {"sources": [f for f in files if ext_of(f) in SOURCE_EXTS and not is_test_source(f)],
            "headers": [f for f in files if ext_of(f) in HEADER_EXTS],
            "tests": [f for f in files if is_test_source(f)], "cmake": None, "make": None, "lang": None, "std": None}
    main_files = info["sources"] or info["tests"] or files          # 以非測試的原始檔為準（C 函式庫常用 C++ 的 gtest 測試）
    if any(ext_of(f) in CPP_SOURCE_EXTS or ext_of(f) in (".hpp", ".hh", ".hxx", ".h++") for f in main_files):
        info["lang"] = "C++"
    elif files:
        info["lang"] = "C"
    build_text, generated = "", set()
    if os.path.isfile(os.path.join(root, "CMakeLists.txt")):
        texts = []
        for p, _ in cc.iter_files(root, glob="CMakeLists.txt") + cc.iter_files(root, exts={".cmake"}):
            try:
                texts.append(cc.read_text(p))
            except OSError:
                pass
        build_text = "\n".join(texts)
        info["cmake"] = {"tests": bool(_CMAKE_TEST_RE.search(build_text))}
        generated |= {os.path.basename(h) for line in build_text.splitlines() if _CMAKE_GEN_LINE_RE.search(line)
                      for h in _HEADER_TOKEN_RE.findall(line)}
        m = re.search(r"CMAKE_CXX_STANDARD\s+(\d+)", build_text) or re.search(r"cxx_std_(\d+)", build_text)
        if m:
            info["std"] = f"c++{m.group(1)}"
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    plain = [n for n in _MAKEFILE_NAMES if n in names]
    dedicated = [n for n in names if _TEST_MAKEFILE_RE.match(n) and os.path.isfile(os.path.join(root, n))]
    for name in plain + dedicated:
        try:
            text = cc.read_text(os.path.join(root, name))
        except OSError:
            continue
        build_text += "\n" + text
        targets = make_targets(text)
        generated |= {os.path.basename(t) for t in targets if _HEADER_TOKEN_RE.fullmatch(t)}    # 標頭是 make 的目標＝產生的
        target = next((t for t in ("test", "check", "tests") if t in targets), None)
        if target and info["make"] is None:
            info["make"] = (name, target)
    if not info["std"]:
        m = re.search(r"-std=((?:c|gnu)\+\+\d+\w*)", build_text)
        if m:
            info["std"] = m.group(1)
    info["base"] = ""
    info["deps"] = declared_deps(root)
    info["ros"] = ros_build_type(root)
    # 建置時才產生的標頭（見 missing_kind）：CMake 的 configure_file／add_custom_command(OUTPUT …)／GENERATED… 那幾行提到的、
    # Makefile 裡當目標的標頭檔名；專案自己定義的 ROS 2 介面（msg/Foo.msg → <套件>/msg/foo.hpp）
    info["generated"] = generated
    info["interfaces"] = ros_interfaces(root)
    m = _PKG_NAME_RE.search(_read(os.path.join(root, "package.xml"))) or _CMAKE_PROJECT_RE.search(build_text)
    info["name"] = m.group(1) if m else None
    return info


def describe(info):
    """repo_map 的一句話：建置系統與 C／C++ 測試怎麼跑。"""
    parts = []
    if info["cmake"]:
        parts.append("CMake" + ("（有註冊測試，code_test 會建置後跑 ctest）" if info["cmake"]["tests"] else "（沒有註冊測試）"))
    if info["make"]:
        name, target = info["make"]
        parts.append(f"{name} 有 {target} 目標（code_test 會跑 make{'' if name in _MAKEFILE_NAMES else ' -f ' + name} {target}）")
    if info["tests"] and not (info["cmake"] and info["cmake"]["tests"]) and not info["make"]:
        parts.append(f"{len(info['tests'])} 個 C／C++ 測試檔（{'根目錄' if info.get('base') == '' else ''}沒有建置檔：code_test 直接用 {'g++' if info['lang'] == 'C++' else 'gcc'} 編譯，"
                     f"連結 gtest）")
    if not parts and info["sources"]:
        parts.append("沒有建置檔，也沒有 C／C++ 測試")
    if info.get("ros") and not ros_sourced():
        parts.append(f"ROS 2 套件（{info['ros']}），這台主機沒有載入 ROS 2：用到 rclcpp 的 C／C++ 檔編譯不了，code_check 只做結構檢查、"
                     "code_test 只跑不依賴 ROS 的 gtest 與 pytest")
    return "；".join(parts)


# ---------------------------------------------------------------- 工作區裡的子專案（ROS 2 colcon 工作區）與外部依賴
_PKG_DEP_RE = re.compile(r"<(?:\w+_)?depend(?:\s[^>]*)?>\s*([A-Za-z][\w\-]*)\s*</")
_PKG_NAME_RE = re.compile(r"<name>\s*([A-Za-z][\w\-]*)\s*</name>")
_PKG_BUILD_TYPE_RE = re.compile(r"<build_type>\s*([\w\-]+)\s*</build_type>")
_CMAKE_PROJECT_RE = re.compile(r"^\s*project\s*\(\s*([\w\-]+)", re.I | re.M)
_CMAKE_FIND_RE = re.compile(r"\bfind_package\s*\(\s*([A-Za-z][\w\-]*)", re.I)
_CMAKE_DEP_LIST_RE = re.compile(r"\b(pkg_check_modules|pkg_search_module|ament_target_dependencies|ament_export_dependencies)"
                                r"\s*\(([^)]*)\)", re.I)
_CMAKE_KEYWORDS = {"required", "quiet", "config", "module", "components", "optional_components", "imported_target", "global",
                   "no_module", "exact", "public", "private", "interface", "system"}
_ROS_IFACE_RE = re.compile(r"^(\w+)/(msg|srv|action)/(?:detail/)?([a-z0-9_]+?)(?:__\w+)?\.(?:h|hpp)$")  # ROS 2 介面（建置時產生）
_TOP_ALIASES = {"unsupported": "eigen", "opencv2": "opencv", "nlohmann": "nlohmann_json", "gmock": "gtest",
                "pcl_ros": "pcl_ros", "boost": "boost", "glog": "glog", "gflags": "gflags", "spdlog": "spdlog", "fmt": "fmt"}
_HEADER_TOKEN_RE = re.compile(r"[\w./${}-]+\.(?:h|hh|hpp|hxx)\b")
_CMAKE_GEN_LINE_RE = re.compile(r"configure_file|\bOUTPUT\b|GENERATED|generate", re.I)
_ANY_INCLUDE_RE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"]+)[>"]', re.M)


def _read(path):
    try:
        return cc.read_text(path)
    except OSError:
        return ""


def project_dir(root, rel):
    """rel（相對 root 的檔案）所屬的子專案目錄（相對 root；"" 是 root 本身）：從檔案所在的目錄往上，最近的有 package.xml
    （ROS 套件）或有 project() 的 CMakeLists.txt 的目錄。colcon 工作區裡每個套件有自己的 include／、依賴與建置檔，要分開看
    （#include "my_pkg/x.hpp" 對的是 src/my_pkg/include）。"""
    d = os.path.dirname(os.path.normpath(rel))
    while d and d not in (".", os.sep) and not d.startswith(".."):
        full = os.path.join(root, d)
        if os.path.isfile(os.path.join(full, "package.xml")) or _CMAKE_PROJECT_RE.search(_read(os.path.join(full, "CMakeLists.txt"))):
            return d
        d = os.path.dirname(d)
    return ""


def ros_build_type(path):
    """path 目錄是需要 ROS 才建置得了的 C／C++ 套件時回 build_type（ament_cmake、catkin…），不是回 None。ament_python 不算
    （沒有 C／C++），build_type 是 cmake 的（colcon 工作區裡的一般 CMake 專案，例如 g2o）也不算：不需要 ROS 就能用 CMake 建置。"""
    xml = _read(os.path.join(path, "package.xml"))
    cm = _read(os.path.join(path, "CMakeLists.txt"))
    m = _PKG_BUILD_TYPE_RE.search(xml)
    kind = m.group(1) if m else ("catkin" if re.search(r"<buildtool_depend>\s*catkin\b", xml) else "ament_cmake" if xml else None)
    if re.search(r"\bament_package\s*\(", cm):
        kind = kind or "ament_cmake"
    elif re.search(r"\bcatkin_package\s*\(", cm):
        kind = kind or "catkin"
    return kind if kind and (kind.startswith("ament_cmake") or kind == "catkin") else None


def _snake(name):
    """ROS 2 介面的檔名 → rosidl 產生的標頭名稱（ShmPayload → shm_payload）。"""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def ros_interfaces(path):
    """path 目錄自己定義的 ROS 2 介面 → {"msg/shm_payload", "srv/…"}（產生的標頭用的 snake_case 名稱）。"""
    out = set()
    for kind in ("msg", "srv", "action"):
        try:
            names = os.listdir(os.path.join(path, kind))
        except OSError:
            continue
        out |= {f"{kind}/{_snake(os.path.splitext(n)[0])}" for n in names if n.endswith("." + kind)}
    return out


def ros_sourced():
    """這個程式的環境有沒有載入 ROS 2（source /opt/ros/<版本>/setup.bash 之後才有 AMENT_PREFIX_PATH）。"""
    return bool(os.environ.get("AMENT_PREFIX_PATH"))


def ros_packages(root, rels):
    """rels（相對 root 的檔案）裡的 ROS 套件 → [(目錄, 名稱, build_type)]，依目錄排序。給 repo_map 列 colcon 工作區的套件。"""
    out = []
    for rel in sorted(rels):
        if os.path.basename(rel) == "package.xml":
            d = os.path.dirname(rel)
            xml = _read(os.path.join(root, rel))
            m, t = _PKG_NAME_RE.search(xml), _PKG_BUILD_TYPE_RE.search(xml)
            out.append((d or ".", m.group(1) if m else os.path.basename(d or root), t.group(1) if t else ros_build_type(os.path.join(root, d)) or "?"))
    return out


def declared_deps(path):
    """path 目錄的 package.xml 與 CMakeLists.txt 宣告的依賴（小寫）：<depend>、<build_depend>…、find_package、pkg_check_modules、
    ament_target_dependencies。用來分辨找不到的標頭是外部函式庫的（這台主機沒裝），還是專案自己的檔案。專案自己的名稱不算。"""
    xml = _read(os.path.join(path, "package.xml"))
    cm = _read(os.path.join(path, "CMakeLists.txt"))
    deps = {d.lower() for d in _PKG_DEP_RE.findall(xml)} | {d.lower() for d in _CMAKE_FIND_RE.findall(cm)}
    for kind, args in _CMAKE_DEP_LIST_RE.findall(cm):
        toks = args.split()
        if kind.lower().startswith(("ament_target", "pkg_")):
            toks = toks[1:]                 # 第一個是目標名稱（常常是 ${PROJECT_NAME}）／變數前綴
        deps |= {t.lower() for t in toks if re.fullmatch(r"[A-Za-z][\w\-]*", t) and t.lower() not in _CMAKE_KEYWORDS}
    own = set(_PKG_NAME_RE.findall(xml)) | set(_CMAKE_PROJECT_RE.findall(cm))
    return deps - {o.lower() for o in own}


def _dir_names(info):
    return {part for h in info.get("headers") or [] for part in h.replace(os.sep, "/").split("/")[:-1]}


def missing_kind(want, info):
    """找不到的標頭 want 是哪一種：
    - "generated"：建置時才產生——ROS 2 介面（xxx_msgs/msg/y.hpp；專案自己的介面要有對應的 msg/Y.msg）、建置檔產生的檔案
      （CMake 的 configure_file／add_custom_command(OUTPUT …)、Makefile 的目標，見 detect 的 generated）；
    - "external"：宣告過的外部依賴（rclcpp/rclcpp.hpp ↔ rclcpp、Eigen/Dense ↔ Eigen3、opencv2/… ↔ OpenCV）；
    - None：專案自己的標頭找不到（拼錯、還沒建立、-I 不對），照樣算錯誤。專案裡有同名的目錄（include/my_pkg）時不會當成外部的。"""
    want = want.replace("\\", "/")
    own = _dir_names(info)
    m = _ROS_IFACE_RE.match(want)
    if m:
        if m.group(1) in own or m.group(1) == info.get("name"):
            return "generated" if f"{m.group(2)}/{m.group(3)}" in (info.get("interfaces") or ()) else None
        return "external" if m.group(1).lower() in (info.get("deps") or set()) else "generated"
    if os.path.basename(want) in (info.get("generated") or ()):
        return "generated"
    deps = info.get("deps") or set()

    def norm(x):
        return re.sub(r"[\d_.-]+$", "", x.lower())

    names = {norm(d) for d in deps} | {d.lower() for d in deps}
    if "/" not in want:
        # 沒有目錄的：<QDialog>、<QtWidgets>（宣告了 Qt）、proj.h ↔ PROJ、sqlite3.h ↔ SQLite3；專案裡有同名的檔案就不算
        stem = os.path.splitext(want)[0]
        if want in {os.path.basename(h) for h in info.get("headers") or ()}:
            return None
        if want[:1] == "Q" and any(n.startswith("qt") for n in names):
            return "external"
        return "external" if stem.lower() in names or norm(stem) in names else None
    top = want.split("/", 1)[0]
    if top in own:
        return None
    top_l = _TOP_ALIASES.get(top.lower(), top.lower())
    if top_l.startswith("qt") and any(n.startswith("qt") for n in names):
        return "external"
    return "external" if top_l in names or norm(top_l) in names else None


def external_header(want, info):
    """找不到的標頭不是專案自己的錯（外部依賴、或建置時才產生）：這台主機沒辦法用編譯器檢查那個檔案。"""
    return missing_kind(want, info) is not None


def unresolved_project_includes(root, rel, info):
    """rel 裡看起來是專案自己的（第一層目錄是專案裡的目錄，例如 my_pkg/…）、卻在專案裡找不到的 #include → [(行號, 標頭)]。
    編譯器碰到第一個缺的外部標頭（rclcpp）就停了，排在後面的專案標頭寫錯它看不到：這裡補上。"""
    text = _read(os.path.join(root, rel))
    names = _dir_names(info)
    known = set(info.get("headers") or [])
    out = []
    for m in _ANY_INCLUDE_RE.finditer(text):
        inc = m.group(1).strip()
        if "/" not in inc or inc.split("/", 1)[0] not in names or missing_kind(inc, info):
            continue
        if os.path.normpath(os.path.join(os.path.dirname(rel), inc)) in known or any(h == inc or h.endswith("/" + inc) for h in known):
            continue
        out.append((text.count("\n", 0, m.start()) + 1, inc))
    return out


def missing_headers(output):
    """gcc 輸出裡「fatal error: X: No such file or directory」的 X（依出現順序、不重複）。"""
    return list(dict.fromkeys(_MISSING_INC_RE.findall(output or "")))


def needed_include_dirs(root, rel, headers, limit=60):
    """rel 直接或間接 #include 的專案標頭需要的 -I 目錄：依標頭路徑的結尾比對（#include "my_pkg/filter.hpp" 對上
    src/my_pkg/include/my_pkg/filter.hpp → src/my_pkg/include）。同名的有好幾個時取跟 rel 共同路徑最長的。"""
    index = {}
    for h in headers:
        index.setdefault(os.path.basename(h), []).append(h)
    known = set(headers)
    dirs, seen, queue = [], set(), [rel]
    while queue and len(seen) < limit:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        for inc in _ANY_INCLUDE_RE.findall(_read(os.path.join(root, cur))):
            inc = inc.strip()
            local = os.path.normpath(os.path.join(os.path.dirname(cur), inc))
            if local in known:                      # 相對於這個檔案所在的目錄（"…" 的寫法編譯器先找這裡）
                queue.append(local)
                continue
            cands = [h for h in index.get(os.path.basename(inc), []) if h == inc or h.endswith("/" + inc)]
            if not cands:
                continue
            best = max(cands, key=lambda h: len(os.path.commonprefix([h, cur])))
            prefix = best[:len(best) - len(inc)].rstrip("/") or "."
            if prefix not in dirs:
                dirs.append(prefix)
            queue.append(best)
    return dirs


def build_command(root):
    """專案本身的建置指令（沒有測試可跑時，整體驗證用它確認整個專案編得過、連結得起來）：根目錄的 Makefile 有預設目標就是
    make -B（全部重新編譯：別的 makefile——例如測試用的、帶 coverage 旗標的——留下的 .o 不能沿用，不然會出現跟程式無關的連結錯誤），
    有 CMakeLists.txt 就是 cmake 設定＋建置；都沒有回 None。ROS 套件（ament_cmake／catkin）在沒有載入 ROS 2 的機器上建置不了
    （find_package(ament_cmake) 就失敗，不是程式的問題）：回 None。"""
    if ros_build_type(root) and not ros_sourced():
        return None
    for name in _MAKEFILE_NAMES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                text = cc.read_text(path)
            except OSError:
                continue
            if any(not t.startswith(".") for t in re.findall(r"^([A-Za-z0-9_.\-/$(){}]+)\s*:(?!=)", text, re.M)):
                return "make -B" if name in ("makefile", "Makefile", "GNUmakefile") else f"make -B -f {name}"
    if os.path.isfile(os.path.join(root, "CMakeLists.txt")):
        return "cmake -S . -B build && cmake --build build -j 8"
    return None


# ---------------------------------------------------------------- 編譯參數（code_check 用 -fsyntax-only）
def _load_compdb(root):
    for cand in [os.path.join(root, "compile_commands.json")] + \
            [os.path.join(root, d, "compile_commands.json") for d in sorted(os.listdir(root)) if d.startswith(("build", "cmake-build"))]:
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            out = {}
            for e in data if isinstance(data, list) else []:
                d = e.get("directory") or root
                fp = e.get("file") or ""
                out[os.path.realpath(os.path.join(d, fp))] = e
            return out
    return {}


def include_dirs(root, info):
    base = info.get("base") or ""
    dirs = [base or "."] + [os.path.join(base, d) for d in ("include", "inc", "src") if os.path.isdir(os.path.join(root, base, d))]
    for h in info["headers"]:
        d = os.path.dirname(h)
        if d and d not in dirs:
            dirs.append(d)
        if len(dirs) >= 30:
            break
    return dirs


# 標準 C／POSIX 標頭的檔名：專案的目錄裡有同名的檔案（fmt 附的 time.h、locale.h…）時，那個目錄不能用 -I（系統標頭的
# #include <time.h> 會找到它，整個標準函式庫編譯失敗——實測 stella_vslam_ros 的 spdlog/fmt/bundled），改用 -iquote
_STD_HEADER_NAMES = {
    "assert.h", "complex.h", "ctype.h", "errno.h", "fenv.h", "float.h", "inttypes.h", "iso646.h", "limits.h", "locale.h", "math.h",
    "setjmp.h", "signal.h", "stdalign.h", "stdarg.h", "stdatomic.h", "stdbool.h", "stddef.h", "stdint.h", "stdio.h", "stdlib.h",
    "stdnoreturn.h", "string.h", "tgmath.h", "threads.h", "time.h", "uchar.h", "wchar.h", "wctype.h", "unistd.h", "fcntl.h",
    "pthread.h", "sched.h", "semaphore.h", "poll.h", "termios.h", "dirent.h", "dlfcn.h", "endian.h", "features.h", "alloca.h",
    "memory.h", "strings.h", "syslog.h", "utime.h", "netdb.h", "glob.h", "regex.h", "spawn.h", "aio.h", "malloc.h"}


def include_flags(root, dirs):
    """include 目錄 → 編譯參數：一般用 -I；目錄裡有跟系統標頭同名的檔案時用 -iquote（只給 #include "…" 用）。"""
    out = []
    for d in dirs:
        try:
            names = set(os.listdir(os.path.join(root, d)))
        except OSError:
            names = set()
        out.append(("-iquote" if names & _STD_HEADER_NAMES else "-I") + d)
    return out


def is_c_file(rel, info):
    e = ext_of(rel)
    return e == ".c" or (e == ".h" and info.get("lang") == "C")


def syntax_command(root, rel, info, compdb=None):
    """(指令 list, cwd)：用編譯器檢查一個檔案、不留下檔案。原始檔完整編譯到 /dev/null（-fsyntax-only 不做流程分析，
    抓不到「非 void 函式忘了 return」）；標頭用 -fsyntax-only。最後一個參數一定是檔案路徑。"""
    full = os.path.realpath(os.path.join(root, rel))
    mode = ["-fsyntax-only"] if ext_of(rel) in HEADER_EXTS else ["-c", "-o", os.devnull]
    entry = (compdb if compdb is not None else _load_compdb(root)).get(full)
    if entry:
        args = entry.get("arguments") or shlex.split(entry.get("command") or "")
        out, skip = [args[0]], False
        for a in args[1:]:
            if skip:
                skip = False
                continue
            if a in ("-o", "-MF", "-MT", "-MQ"):
                skip = True
                continue
            if a in ("-c", "-MD", "-MMD") or a.startswith(("-o", "-MF")) or \
                    os.path.realpath(os.path.join(entry.get("directory") or root, a)) == full:
                continue
            out.append(a)
        return out + mode + ["-fdiagnostics-color=never", full], entry.get("directory") or root
    c = is_c_file(rel, info)
    cmd = [os.environ.get("CC", "gcc") if c else os.environ.get("CXX", "g++")] + mode + ["-fdiagnostics-color=never"]
    if ext_of(rel) in HEADER_EXTS:
        cmd += ["-x", "c-header" if c else "c++-header"]
    if not c:
        cmd.append(f"-std={info.get('std') or 'c++17'}")
    dirs = include_dirs(root, info)
    cmd += include_flags(root, dirs + [d for d in needed_include_dirs(root, rel, info["headers"]) if d not in dirs])
    return cmd + [rel], root


def includes_of(text):
    return re.findall(r'^[ \t]*#[ \t]*include[ \t]*"([^"]+)"', text, re.M)


# ---------------------------------------------------------------- 輸出的整理
_DIAG_RE = re.compile(r"^(?P<loc>[^\s:][^:\n]*:\d+(?::\d+)?):\s*(?P<kind>fatal error|error|warning|note):\s*(?P<msg>.*)$")
_SRC_LINE_RE = re.compile(r"^\s*\d*\s*\|")
_LINK_RE = re.compile(r"undefined reference to|multiple definition of|cannot find -l\S+|undefined symbol|"
                      r"relocation .* against|ld returned \d+ exit status")
_NOISE_RE = re.compile(r"#pragma once in main file")


def _rel_loc(loc, roots):
    for r in roots:
        if r and loc.startswith(r.rstrip("/") + "/"):
            return loc[len(r.rstrip("/")) + 1:]
    return loc


def diagnostics(output, roots=(), max_errors=12, with_warnings=False):
    """gcc／g++／ld 的輸出 → {"errors": [區塊文字], "n_errors", "warnings": [...], "link": [行]}。
    每個錯誤附上 gcc 接著印的原始碼行與 ^ 指標（看得出是哪裡）；同一個錯誤（同檔同行同訊息）只列一次。"""
    lines = (output or "").splitlines()
    errors, warns, seen = [], [], set()
    i = 0
    while i < len(lines):
        m = _DIAG_RE.match(lines[i])
        if not m or m.group("kind") == "note" or _NOISE_RE.search(m.group("msg")):
            i += 1
            continue
        kind = m.group("kind")
        loc = _rel_loc(m.group("loc"), roots)
        block = [f"{loc}: {kind}: {m.group('msg')}"]
        j = i + 1
        while j < len(lines) and _SRC_LINE_RE.match(lines[j]) and len(block) < 5:
            block.append(lines[j])
            j += 1
        notes = 0
        while j < len(lines) and notes < 2:
            mn = _DIAG_RE.match(lines[j])
            if not (mn and mn.group("kind") == "note"):
                break
            block.append(f"  {_rel_loc(mn.group('loc'), roots)}: note: {mn.group('msg')}")
            j += 1
            notes += 1
            while j < len(lines) and _SRC_LINE_RE.match(lines[j]):
                j += 1
        key = (loc.split(":")[0], loc.split(":")[1] if ":" in loc else "", m.group("msg"))
        if key not in seen:
            seen.add(key)
            (errors if kind in ("error", "fatal error") else warns).append("\n".join(block))
        i = j
    link = list(dict.fromkeys(ln.strip() for ln in lines if _LINK_RE.search(ln) and "collect2" not in ln))
    return {"errors": errors[:max_errors], "n_errors": len(errors), "warnings": warns[:max_errors] if with_warnings else [],
            "n_warnings": len(warns), "link": link[:12], "hints": include_hints(output, roots[0] if roots else None)}


_MISSING_INC_RE = re.compile(r"fatal error: ([^:\s]+): No such file or directory")


def include_hints(output, root):
    """「fatal error: X: No such file or directory」：X 其實在專案裡別的路徑時，說明 #include 跟 -I 要怎麼對上
    （實測 e4b 寫 #include "include/Circle.hpp"、makefile 用 -Iinclude，同一個修改送了三次）。"""
    hints = []
    if not root or not os.path.isdir(root):
        return hints
    files = None
    for want in dict.fromkeys(_MISSING_INC_RE.findall(output or "")):
        if files is None:
            files = [rel for _, rel in cc.iter_files(root, exts=ALL_EXTS)]
        base = os.path.basename(want)
        cands = [f for f in files if f == want or f.endswith("/" + want)] or [f for f in files if os.path.basename(f) == base]
        if cands:
            used = [x.rstrip("/") for x in dict.fromkeys(re.findall(r"(?:^|\s)-I\s?([^\s]+)", output or "", re.M))]
            under = [(x, os.path.relpath(cands[0], x)) for x in used if x not in (".", "") and cands[0].startswith(x + "/")]
            if under:
                how = f"現在的編譯參數有 -I{under[0][0]}，所以要寫 #include \"{under[0][1]}\""
            elif "/" in want and cands[0].endswith("/" + want):
                how = (f"#include 的寫法對得上檔案的位置，是編譯參數少了 -I{cands[0][:-len(want) - 1]}"
                       "（在建置檔加上這個 include 目錄；#include 不用改）")
            else:
                d = os.path.dirname(cands[0])
                how = (f"用 -I{d} 時寫 #include \"{os.path.basename(cands[0])}\"，" if d else "") + "或在建置檔的編譯參數加上 -I."
            hints.append(f"找不到 #include 的「{want}」，但專案裡有 {'、'.join(cands[:3])}：#include 的路徑是相對於 -I 的目錄"
                         f"（或 .cpp 所在的目錄）——{how}")
        else:
            hints.append(f"找不到 #include 的「{want}」，專案裡也沒有這個檔案：檔名拼錯、還沒建立，或是需要另外安裝的函式庫")
    return hints


def format_diagnostics(d, what="編譯"):
    """diagnostics() 的結果 → 給模型看的文字（沒有錯誤回空字串）。"""
    parts = []
    if d["errors"]:
        more = f"（只列前 {len(d['errors'])} 個）" if d["n_errors"] > len(d["errors"]) else ""
        parts.append(f"{what}錯誤 {d['n_errors']} 個{more}：\n" + "\n".join(d["errors"]))
    if d["link"]:
        parts.append("連結錯誤（宣告了卻沒有實作、實作的簽名跟宣告不一樣、同一個函式定義了兩次、或少連結了檔案／程式庫）：\n"
                     + "\n".join(d["link"]))
    if d.get("hints"):
        parts.append("提示：\n" + "\n".join(f"- {h}" for h in d["hints"]))
    return "\n".join(parts)


_GT_RUN_RE = re.compile(r"^\[ RUN      \] (\S+)")
_GT_END_RE = re.compile(r"^\[ +(OK|FAILED|SKIPPED) +\] (\S+)")


def gtest_failures(output, max_blocks=8, max_lines=16):
    """gtest 輸出裡每個失敗的測試：[ RUN ] 到 [ FAILED ] 之間的訊息（檔案:行號: Failure、期望值與實際值）。
    回傳 (區塊 list, 失敗的總數, 跑到一半當掉的測試名稱或 None)。"""
    blocks, total = [], 0
    cur, buf = None, []
    for ln in (output or "").splitlines():
        m = _GT_RUN_RE.match(ln)
        if m:
            cur, buf = m.group(1), []
            continue
        if cur is None:
            continue
        m = _GT_END_RE.match(ln)
        if m and m.group(2) == cur:
            if m.group(1) == "FAILED":
                total += 1
                if len(blocks) < max_blocks:
                    body = buf[:max_lines] + ([f"  …（還有 {len(buf) - max_lines} 行）"] if len(buf) > max_lines else [])
                    blocks.append(f"✗ {cur}\n" + "\n".join("  " + x for x in body))
            cur = None
            continue
        buf.append(ln)
    return blocks, total, cur


def ctest_failed(output):
    """ctest 的「The following tests FAILED」清單 → [(名稱, 原因)]。"""
    out, on = [], False
    for ln in (output or "").splitlines():
        if "The following tests FAILED" in ln:
            on = True
            continue
        if on:
            m = re.match(r"^\s*\d+\s*-\s*(.+?)\s*\(([^)]*)\)\s*$", ln)
            if m:
                out.append((m.group(1), m.group(2)))
            elif ln.strip():
                break
    return out
