"""CodingWorker：coding job 的一項（work item）由一個 worker 完成——乾淨的 session、自己的工具迴圈、做完由程式驗證。

跟主對話一樣，每一步模型回一個 JSON {thought, reply, action}（format=AGENT_REPLY_SCHEMA，只看 action）；不一樣的地方：
- 沒有「先載入規格」這一步：worker 的工具與語法直接寫在 coding_agents/worker.md，填技能名稱或腳本路徑都可以，
  只能用 CODING_WORKER_SCRIPTS 裡的腳本（看、搜、改、測、跑）。
- 改檔的「內容」不放在 JSON：worker 決定 code_edit／code_write 某個檔案後，harness 再呼叫一次模型（不加 format=），
  請它用一般文字輸出整份檔案或 SEARCH/REPLACE 區塊（內容通道），存成 payload 交給腳本。實測 e4b 把程式碼塞進 JSON 字串時
  反斜線會少跳脫一層（3/3 錯），放在 ``` 區塊裡 3/3 對；改既有檔案時整份重寫 5/5 對、SEARCH/REPLACE 2/5 對（行號被抄進去、
  縮排錯位），所以 CODING_WHOLE_FILE_MAX_LINES 以內的檔案請它輸出整份，更長的才用區塊（腳本會剝行號、平移縮排）。
- 回報完成（action 為 null）時由程式驗證：改過的檔案做靜態檢查（語法、未定義名稱、跨檔匯入），再跑這一項的驗證指令；
  沒過就把錯誤交還給 worker 修（最多 CODING_VERIFY_ROUNDS 次）。
- 上下文快滿時把舊的工具回傳換成一行摘要（同 claude_code 模式的清除，不呼叫模型）。
每一步的完整內容寫在 logs/coding_jobs/<編號>/workers/item<N>_try<K>.md，事件同步推給 Web 的 Coding 面板。
"""
import json
import os
import re
import time
from skills_system.scripts import _code_common as cc
from skills_system.scripts import _cpp_common as cpp
from skills_system.scripts import repo_map_cmd
from .config import (
    CODING_CONTENT_MAX_PREDICT,
    CODING_COVERAGE_ROUNDS,
    CODING_COVERAGE_TARGET,
    CODING_EDIT_CONTEXT_MAX_LINES,
    CODING_FILE_PREVIEW_MAX_LINES,
    CODING_PAYLOAD_SCRIPTS,
    CODING_RUN_TIMEOUT,
    CODING_TOOL_RESULT_MAX_CHARS,
    CODING_VERIFY_ROUNDS,
    CODING_WHOLE_FILE_MAX_LINES,
    CODING_WORKER_CTX_RATIO,
    CODING_WORKER_MAX_STEPS,
    CODING_WORKER_SCRIPTS,
    NUM_CTX,
    THINK_EXTRA_PREDICT,
)
from .protocol import action_text, parse_agent_reply
from .schemas import AGENT_REPLY_SCHEMA

# worker 沒有兩階段揭露：技能名稱直接對到腳本（主對話不能這樣做，見 dispatch.run_tool）
WORKER_SKILL_SCRIPTS = {
    "code_view": "code_view_cmd.py", "code_search": "code_search_cmd.py", "code_refs": "code_refs_cmd.py",
    "repo_map": "repo_map_cmd.py", "code_ast_reader": "code_ast_reader_cmd.py", "code_edit": "code_edit_cmd.py",
    "code_write": "code_write_cmd.py", "code_test": "code_test_cmd.py", "code_run": "code_run_cmd.py",
    "code_check": "code_check_cmd.py", "code_diff": "code_diff_cmd.py", "find_file": "find_file_cmd.py",
    "list_dir": "ls_cmd.py", "view_file": "cat_cmd.py",
}
_BRIEF_FILES_MAX_CHARS = 14000      # 任務說明裡附上的檔案內容總上限（超過的檔案只給大綱）
_CONTENT_SYSTEM = ("你是程式碼撰寫器：照指示輸出檔案的內容。只輸出要求的格式——一個 ``` 程式碼區塊（整份檔案），或 SEARCH/REPLACE "
                   "區塊——不要輸出 JSON、不要解釋、不要加任何其他文字。寫出來的程式碼要能直接執行：需要的 import（C／C++ 是 "
                   "#include）要有，只呼叫已經存在的函式與方法（看【其他相關檔案】裡實際的名稱與參數）。")
_KEEP_RECENT_RESULTS = 3            # 上下文壓縮時保留最近幾則工具回傳的原文


_VIEW_RANGE_RE = re.compile(r"第 (\d+)～(\d+) 行")
_CLOSEST_RE = re.compile(r"最像的是第 (\d+)～(\d+) 行")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_NOT_NAMES = {"self", "None", "True", "False", "return", "import", "class", "from", "with", "code_edit", "code_view", "code_write",
              "pytest", "python", "python3", "test", "tests", "verify", "SEARCH", "REPLACE", "const", "void", "static", "struct"}


def _focus_from_text(content, text):
    """text（這一步的意圖、這一項的目標）提到、在這個檔案裡有定義的名稱 → 第一個定義的行號（1 起算）；找不到回 None。
    Python：def／class；C／C++：行首開始、括號前是這個名稱的定義。"""
    lines = content.split("\n")
    for name in dict.fromkeys(n for n in _NAME_RE.findall(text or "") if n not in _NOT_NAMES):
        pat = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b|^[A-Za-z_][^;{{=]*\b{re.escape(name)}\s*\(")
        for i, line in enumerate(lines):
            if pat.search(line):
                return i + 1
    return None


def _edit_window(lines, focus, max_lines):
    """太長的檔案給 SEARCH/REPLACE 看的那一段：以 focus（(起, 迄) 行號，1 起算）為中心、最多 max_lines 行；沒有 focus 就從開頭。
    SWE-bench 評測（2026-10-09）：以前一律給前 800 行，要改的地方在後面時模型看不到原文、只能憑印象寫 SEARCH，對不上就重來到卡住
    （「SEARCH 對不上」125 次裡 44 次目標在第 800 行之後）。"""
    n = len(lines)
    if n <= max_lines:
        return "\n".join(lines).rstrip()
    start = 0
    if focus:
        center = (focus[0] + focus[1]) // 2 - 1
        start = max(0, min(n - max_lines, center - max_lines // 2))
    end = min(n, start + max_lines)
    head = f"…（前面還有 {start} 行，第 1～{start} 行沒有附上）\n" if start else ""
    tail = f"\n…（後面還有 {n - end} 行，第 {end + 1}～{n} 行沒有附上）" if end < n else ""
    return head + "\n".join(lines[start:end]).rstrip() + tail


def _lang_fence(path):
    return cc.fence_lang(path) or ""


def _looks_like_decision(text):
    """內容通道的回覆是不是又變成 worker 的 JSON 決定（{"thought": …}），而不是檔案內容。"""
    t = (text or "").strip().strip("`").strip()
    if t.startswith("json"):
        t = t[4:].strip()
    if not t.startswith("{"):
        return False
    try:
        data = json.loads(t)
    except ValueError:
        return '"thought"' in t[:200] or '"action"' in t[:400]
    return isinstance(data, dict) and bool({"thought", "action", "reply"} & set(data))


class CodingWorker:
    def __init__(self, orch, job, item, attempt, prev_failure=None):
        self.o = orch
        self.agent = orch.agent
        self.job = job
        self.item = item
        self.attempt = attempt
        self.prev_failure = prev_failure
        self.model = orch.worker_model()
        self.ws = job["workspace"]
        self.messages = []
        self.edited = []            # 這個 worker 改過的檔案（相對路徑，依序）
        self.coverage_rounds = 0    # 只寫測試的工作：因為覆蓋率不夠被交還的次數（見 _coverage_check）
        self.steps = 0
        self.calls = 0
        self.last_reply = ""
        self._last_action = None
        self._same_count = 0
        self._errors = {}           # (動作, 錯誤訊息開頭) → 次數：同一個錯誤第三次就提早結束（見 run）
        self.focus = {}             # 檔案 → (起, 迄)：最近一次 code_view 的範圍、或 SEARCH 對不上時最像的段落（修改視窗以它為中心）
        self.transcript = os.path.join(orch.job_dir(job["id"]), "workers", f"item{item['n']}_try{attempt}.md")

    # ---------------------------------------------------------------- 紀錄
    def _log(self, title, text):
        try:
            os.makedirs(os.path.dirname(self.transcript), exist_ok=True)
            with open(self.transcript, "a", encoding="utf-8") as f:
                f.write(f"\n## {title}（{time.strftime('%H:%M:%S')}）\n\n{text}\n")
        except OSError:
            pass

    def _emit(self, etype, text, **data):
        self.o.emit(self.job, etype, text, item=self.item["n"], **data)

    # ---------------------------------------------------------------- prompt
    def _system(self):
        return self.o.prompt_file("worker.md")

    def _file_block(self, rel, budget):
        """任務說明裡附上的一個檔案：不長就整份（帶行號），太長或超過預算就給結構大綱。回傳 (文字, 用掉的字數)。"""
        path = os.path.join(self.ws, rel)
        if not os.path.isfile(path):
            return f"### {rel}（目前不存在：這一項要新建）", 0
        try:
            text = cc.read_text(path)
        except OSError:
            return f"### {rel}（讀不到）", 0
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        if len(lines) <= CODING_FILE_PREVIEW_MAX_LINES and len(text) <= budget:
            body = cc.numbered(lines)
            return f"### {rel}（{len(lines)} 行，目前的完整內容）\n```{_lang_fence(rel)}\n{body}\n```", len(body)
        outline = self.o.outline_of(path, text)
        return (f"### {rel}（{len(lines)} 行，太長只附結構；要看哪一段用 code_view {rel} --from N --lines M 或 --symbol 名稱）\n"
                f"{outline}"), len(outline)

    def _brief(self):
        it, job = self.item, self.job
        total = len(job["items"])
        files = it.get("files") or []
        lines = [f"[work item {it['n']}/{total}] {it['title']}",
                 f"【整體任務】{job['task']}",
                 f"【這一項要做的事】\n{it['goal']}"]
        if files:
            marks = [f"{f}{'' if os.path.exists(os.path.join(self.ws, f)) else '（新檔）'}" for f in files]
            lines.append("【要修改或建立的檔案】" + "、".join(marks))
        if it.get("context_files"):
            lines.append("【參考檔案（不用修改）】" + "、".join(it["context_files"]))
        where = self.o.mentioned_symbols(self.job, f"{it['title']} {it['goal']}")
        if where:
            kinds = {"class": "類別", "def": "函式", "method": "方法"}
            lines.append("【說明裡提到的名稱，目前定義在】" + "；".join(f"{n}：{rel} 第 {ln} 行（{kinds.get(k, k)}）" for n, rel, k, ln in where)
                         + "。要改它們就改這些檔案。")
        cpp_item = any(cc.language_of(f) in ("C", "C++", "C/C++ 標頭") for f in files)
        checks = ("語法與編譯檢查（gcc／g++）" if cpp_item else "語法、未定義的名稱、跨檔的 import") \
            + (f"，並執行：{it['verify']}" if it.get("verify") else "")
        lines.append(f"【你回報完成後系統會自動驗證】{checks}")
        done = self.o.handoff_notes(job, it["n"])
        if done:
            lines.append(f"【前面已完成的項目（其他 worker 做的，檔案已經是改過的版本）】\n{done}")
        if it.get("notes"):
            lines.append("【使用者的補充說明】\n" + "\n".join(f"- {x}" for x in it["notes"]))
        rules_name, rules = self.o.project_rules(job)
        if rules:
            lines.append(f"【專案的開發規範（{rules_name}，要遵守）】\n{rules}")
        docs, skipped = self.o.task_documents(job)
        if docs:
            lines.append(f"【任務提到的文件（規格：名稱、參數、輸出格式都要照這裡）】\n{docs}")
        if skipped:
            lines.append(f"【任務提到、太長沒有附上的文件（需要時用 code_view 看）】{'、'.join(skipped)}")
        if self.prev_failure:
            lines.append(f"【上一個 worker 做這一項失敗了，原因如下；檔案可能已經被它改過一部分，先看目前的內容再決定怎麼改】\n"
                         f"{cc.clip_middle(self.prev_failure, 2500, '失敗紀錄')}")
        blocks, budget = [], _BRIEF_FILES_MAX_CHARS
        for rel in files:
            b, used = self._file_block(rel, budget)
            blocks.append(b)
            budget = max(0, budget - used)
        for rel in it.get("context_files") or []:
            path = os.path.join(self.ws, rel)
            if os.path.isfile(path):
                try:
                    text = cc.read_text(path)
                except OSError:
                    continue
                blocks.append(f"### {rel}（參考，結構大綱）\n{self.o.outline_of(path, text)}")
        if blocks:
            lines.append("---\n以下是相關檔案目前的內容（行號只是參考，不屬於檔案內容）：\n\n" + "\n\n".join(blocks))
        lines.append("---\n先想好要改哪些地方，再一步一步做；每一步回一個 JSON。")
        return "\n\n".join(lines)

    # ---------------------------------------------------------------- 模型呼叫
    def _chat(self, kind, messages, **kw):
        last = None
        for i in range(3):
            if self.o.cancel_requested(self.job):
                raise _Cancelled()
            try:
                self.calls += 1
                self.job["model_calls"] = self.job.get("model_calls", 0) + 1   # 畫面上即時更新
                return self.agent._timed_chat(kind, model=self.model, messages=messages, **kw)
            except Exception as e:   # Ollama 斷線或逾時：等一下再試
                last = e
                self._emit("error", f"⚠️ 呼叫模型失敗（第 {i + 1} 次）：{e}")
                time.sleep(3 * (i + 1))
        raise RuntimeError(f"呼叫模型連續失敗：{last}")

    def _decide(self):
        think = self.o.think_for("worker")    # 預設關；使用者在設定裡打開、而且模型支援 thinking 才開
        res = self._chat("code_worker", self.messages, format=AGENT_REPLY_SCHEMA,
                         options={"temperature": 0.2, "num_ctx": NUM_CTX}, think=think)
        raw = res["message"]["content"].strip()
        parsed = parse_agent_reply(raw)
        if parsed["valid"] and not parsed["reply"] and not parsed["action"]:   # 空白回覆（多半是英文雙引號提前結束字串）
            nudge = {"role": "user", "content": ("[harness] 你剛才的回覆 reply 是空的、action 是 null。請重新回覆：thought 不要用英文雙引號，"
                                                 "reply 要有內容；還要繼續做就填 action，這一項做完了就在 reply 寫改了什麼、action 填 null。")}
            res = self._chat("code_worker", self.messages + [nudge], format=AGENT_REPLY_SCHEMA,
                             options={"temperature": 0.3, "num_ctx": NUM_CTX}, think=think)
            raw = res["message"]["content"].strip()
            parsed = parse_agent_reply(raw)
        return raw, parsed

    def _content(self, mode, rel, intent):
        """內容通道：一個乾淨的獨立 session（不帶 worker 的 JSON 對話），請模型用一般文字輸出整份檔案或 SEARCH/REPLACE 區塊。
        實測接在 worker 的對話後面時，e4b 幾乎每次都照前面的樣子再回一個 JSON 決定（不是檔案內容），所以內容另外開一個 session：
        只給這一項的目標、worker 這一步想做的修改、最近的錯誤、相關檔案與目標檔案目前的內容。回覆又是 JSON 時加強提醒重試一次。"""
        msgs = [{"role": "system", "content": _CONTENT_SYSTEM}, {"role": "user", "content": self._content_prompt(mode, rel, intent)}]
        think = self.o.think_for("worker")
        # 思考也算在 num_predict 裡：開了 thinking 時多給一段，免得想完就沒有額度寫檔案
        opts = {"temperature": 0.2, "num_ctx": NUM_CTX,
                "num_predict": CODING_CONTENT_MAX_PREDICT + (THINK_EXTRA_PREDICT if think else 0)}
        raw = self._chat("code_content", msgs, options=opts, think=think)["message"]["content"]
        if _looks_like_decision(raw):
            msgs.append({"role": "assistant", "content": raw})
            msgs.append({"role": "user", "content": "這不是檔案內容。不要輸出 JSON：照上面【輸出】的格式，直接輸出程式碼。"})
            raw = self._chat("code_content", msgs, options=opts, think=think)["message"]["content"]
        return raw

    def _related_files(self, rel):
        """內容通道要附的其他相關檔案：這一項的其他檔案、參考檔案、這個 worker 改過的檔案（不長給全文，長的給大綱）。"""
        names = [f for f in (self.item.get("files") or []) + (self.item.get("context_files") or []) + self.edited if f != rel]
        blocks, budget = [], 9000
        for f in list(dict.fromkeys(names))[:6]:
            path = os.path.join(self.ws, f)
            if not os.path.isfile(path):
                continue
            try:
                text = cc.read_text(path)
            except OSError:
                continue
            if text.count("\n") <= 150 and len(text) <= budget:
                blocks.append(f"### {f}\n```{_lang_fence(f)}\n{text.rstrip()}\n```")
                budget -= len(text)
            else:
                outline = self.o.outline_of(path, text)
                blocks.append(f"### {f}（結構大綱）\n{outline}")
                budget -= len(outline)
            if budget <= 0:
                break
        return "\n\n".join(blocks)

    def _recent_problem(self):
        """worker 對話裡最近一則錯誤或驗證失敗（給內容通道參考：這次修改要解決什麼）。"""
        for m in reversed(self.messages[-6:]):
            c = m["content"]
            if m["role"] == "user" and ("[ERROR]" in c[:400] or c.startswith("[驗證失敗]")):
                return cc.clip_middle(c, 2500, "錯誤訊息")
        return ""

    def _content_prompt(self, mode, rel, intent):
        lang = _lang_fence(rel)
        parts = [f"【整體任務（裡面的使用範例、名稱、格式要照抄）】{self.job['task']}"]
        docs, _ = self.o.task_documents(self.job)
        if docs:
            parts.append(f"【任務提到的文件（規格：名稱、參數、輸出格式都要照這裡）】\n{docs}")
        parts += [f"【這一項工作】{self.item['title']}\n{self.item['goal']}", f"【這一步要做的修改】{intent}"]
        problem = self._recent_problem()
        if problem:
            parts.append(f"【最近的錯誤或驗證結果（這次修改要解決的）】\n{problem}")
        related = self._related_files(rel)
        if related:
            parts.append(f"【其他相關檔案（參考用，不要輸出它們）】\n{related}")
        if mode == "write":
            parts.append(f"【要建立的新檔案】{rel}")
            parts.append(f"【輸出】只輸出 {rel} 的完整內容，放在一個 ```{lang} 程式碼區塊裡：從第一行寫到最後一行，不要省略，"
                         f"區塊外面不要寫任何文字。")
            return "\n\n".join(parts)
        try:
            content = cc.read_text(os.path.join(self.ws, rel))
        except OSError:
            content = ""
        if mode == "whole":
            parts.append(f"【要修改的檔案】{rel}（目前的完整內容，沒有行號）：\n```{lang}\n{content.rstrip()}\n```")
            parts.append(f"【輸出】只輸出修改後的「完整檔案」，放在一個 ```{lang} 程式碼區塊裡：照【這一步要做的修改】改；沒有要改的部分"
                         f"一字不漏照抄（不要寫「其餘不變」「...」，不要刪掉原本的註解），區塊外面不要寫任何文字。")
            return "\n\n".join(parts)
        lines = content.split("\n")
        focus = None
        if len(lines) > CODING_EDIT_CONTEXT_MAX_LINES:
            focus = self.focus.get(rel)
            if not focus:
                ln = _focus_from_text(content, intent) or _focus_from_text(content, f"{self.item['title']} {self.item['goal']}")
                focus = (ln, ln) if ln else None
        shown = _edit_window(lines, focus, CODING_EDIT_CONTEXT_MAX_LINES)
        parts.append(f"【要修改的檔案】{rel}（目前的內容，沒有行號）：\n```{lang}\n{shown}\n```")
        parts.append("【輸出】只輸出 SEARCH/REPLACE 區塊（可以有好幾個），格式：\n<<<<<<< SEARCH\n（要被取代的原文：從上面逐字照抄連續幾行，"
                     "包含縮排，不要帶行號）\n=======\n（新的內容）\n>>>>>>> REPLACE\nSEARCH 要夠長、在檔案裡只出現一次；要新增函式時，"
                     "SEARCH 抄它前面那個函式的最後幾行，REPLACE 寫那幾行再接上新函式。區塊外面不要寫任何文字。")
        return "\n\n".join(parts)

    # ---------------------------------------------------------------- 工具
    def _resolve_script(self, command):
        token = os.path.basename(str(command or "").strip())
        if token.endswith(".md"):
            token = token[:-3]
        if token in WORKER_SKILL_SCRIPTS:
            return WORKER_SKILL_SCRIPTS[token]
        name = self.agent._normalize_script_name(token)
        return name if name in CODING_WORKER_SCRIPTS else None

    def _payload_mode(self, script, args):
        """code_edit／code_write 要請模型輸出什麼：write（新檔整份）、whole（既有檔整份）、blocks（SEARCH/REPLACE）。
        回傳 (腳本, 參數, 模式, 錯誤)；--delete 不需要內容（模式 None）。"""
        flags = [a for a in args if a.startswith("--")]
        paths = [a for a in args if not a.startswith("--")]
        if not paths:
            return script, args, None, "[ERROR] 沒有給檔案路徑：args 只要填檔案路徑（例如 inventory/store.py），內容系統會另外請你輸出。"
        rel = paths[0]
        if len(paths) > 1:
            return script, args, None, (f"[ERROR] args 只能有一個檔案路徑（收到 {' '.join(paths[:3])}…）：不要把程式碼放進 args，"
                                        f"系統會另外請你輸出內容。一次改一個檔案。")
        if script == "code_write_cmd.py" and "--delete" in flags:
            return script, [rel, "--delete"], None, None
        full = os.path.realpath(os.path.join(self.ws, rel))
        if not (full == self.ws or full.startswith(self.ws.rstrip(os.sep) + os.sep)):
            return script, args, None, f"[ERROR] {rel} 在工作區 {self.ws} 之外，不能修改；路徑請寫成相對於專案根目錄。"
        exists = os.path.isfile(full)
        if not exists and "/" in rel.strip("/"):
            # 任務常用套件裡的相對路徑（「在 test/test_battery.py 加測試」），真正的檔案是 src/amr_tools/test/test_battery.py。
            # 實測 e4b：code_edit 回「不存在，建立新檔請用 code_write」，它就照著在工作區根目錄建了一個 → 先指出那個檔案
            same = self._same_tail(rel)
            if same:
                verb = "沒有建立" if script == "code_write_cmd.py" else "不存在"
                return script, args, None, (f"[ERROR] {rel} {verb}：專案裡已經有 {'、'.join(same)}——任務或說明寫的路徑是相對於套件的，"
                                            f"要改的是那個檔案，請用那個路徑（路徑一律相對於專案根目錄）。")
        if self.job.get("tests_only") and not cc.is_test_path(rel) and not cc.BUILD_FILE_RE.search(rel):
            return script, args, None, (f"[ERROR] 這個工作只寫測試，不能{'建立' if not exists else '修改'}正式程式 {rel}。測試檔放在測試目錄"
                                        f"（例如 unit_tests/、tests/），檔名 test_*.py、test_*.cpp。覺得程式本身有 bug：測試照目前的行為寫，"
                                        f"或標成預期失敗（pytest.mark.xfail(reason=…)、GTEST_SKIP() << \"…\"），並在完成時的摘要說明。")
        if script == "code_write_cmd.py" and not exists:
            listed = self.o.listed_new_files(self.job)
            is_test = cpp.is_test_source(rel) or re.search(r"(^|/)(test_[^/]*|[^/]*_test)\.py$", rel)
            if len(listed) >= 2 and rel not in listed and rel not in (self.item.get("files") or []) and not is_test:
                # 實測 e4b：計畫已經拿掉 src/Circle.cpp，worker 還是自己建了它、把實作寫進去，官方的建置檔不編它 → 測試連結失敗
                mine = "、".join(self.item.get("files") or []) or "（這一項沒有列檔案）"
                return script, args, None, (f"[ERROR] 任務列出的檔案沒有 {rel}，不能新建：這一項的檔案是 {mine}，內容寫在那裡"
                                            f"（C++ 只有標頭的類別，方法直接寫在標頭裡、或標成 inline）。任務列出的檔案："
                                            f"{'、'.join(listed)}")
            return script, [rel], "write", None
        if not exists:
            similar = [f for f in self._ws_files() if os.path.basename(f) == os.path.basename(rel)][:5]
            if similar:
                return script, args, None, (f"[ERROR] {rel} 不存在。專案裡同名的檔案：{'、'.join(similar)}——要改的是那個就用那個路徑；"
                                            f"確定要建立新檔才用 code_write（scripts/code_write_cmd.py {rel}）。")
            return script, args, None, f"[ERROR] {rel} 不存在：建立新檔請用 code_write（scripts/code_write_cmd.py {rel}）。"
        try:
            n_lines = cc.read_text(full).count("\n") + 1
        except OSError:
            n_lines = 0
        whole = "--whole" in flags or n_lines <= CODING_WHOLE_FILE_MAX_LINES
        return "code_edit_cmd.py", [rel] + (["--whole"] if whole else []), ("whole" if whole else "blocks"), None

    def _ws_files(self):
        if getattr(self, "_files_cache", None) is None:
            self._files_cache = [rel for _, rel in cc.iter_files(self.ws)]
        return self._files_cache

    def _same_tail(self, rel):
        """工作區裡路徑結尾是 rel 的檔案（rel 至少有一層目錄）：這一項的檔案清單優先，再找整個工作區。"""
        tail = "/" + rel.strip("/")
        mine = [f for f in self.item.get("files") or [] if f.endswith(tail) and os.path.isfile(os.path.join(self.ws, f))]
        return mine or [f for f in self._ws_files() if f.endswith(tail)][:3]

    def _run_tool(self, parsed):
        """執行一個 action，回傳 (給模型看的結果, 給事件看的摘要 dict)。"""
        action = parsed["action"]
        script = self._resolve_script(action["command"])
        if not script:
            allowed = "、".join(sorted(WORKER_SKILL_SCRIPTS))
            return (f"[ERROR] worker 不能使用 {action['command']}。可以用的工具：{allowed}（command 填 scripts/<名稱>_cmd.py "
                    f"或技能名稱）。"), {"command": action_text(action), "status": "ERROR"}
        args = self.agent._parse_script_args(script, action.get("args") or "")
        args = [a for i, a in enumerate(args) if a != "--payload" and (i == 0 or args[i - 1] != "--payload")]
        payload_path, mode = None, None
        if script in CODING_PAYLOAD_SCRIPTS:
            script, args, mode, err = self._payload_mode(script, args)
            if err:
                return err, {"command": f"{script} {' '.join(args)}", "status": "ERROR"}
            if mode:
                rel = args[0]
                intent = "；".join(x for x in (parsed.get("thought"), parsed.get("reply")) if x) or "照這一項的要求修改"
                raw = self._content(mode, rel, intent)
                self._log(f"內容通道（{mode}）：{rel}", f"````\n{raw}\n````")
                payload_path = self.o.save_payload(self.job, self.item["n"], self.steps, raw)
                args = args + ["--payload", payload_path]
        out = self.o.run_script(self.job, script, args)
        status = "ERROR" if out.lstrip().startswith("[ERROR]") else "PASS"
        out = self._after_tool(script, args, mode, status, out)
        if script in CODING_PAYLOAD_SCRIPTS and status == "PASS" and args:
            rel = os.path.relpath(os.path.realpath(os.path.join(self.ws, args[0])), self.ws)
            if rel not in self.edited:
                self.edited.append(rel)
        shown_args = [a for a in args if a != "--payload" and a != payload_path]
        return out, {"command": f"{script} {' '.join(shown_args)}".strip(), "status": status, "mode": mode}

    def _outline_names(self, rel, limit=30):
        """檔案現在的結構（類別、函式與行號），一行列完；讀不到或沒有結構回空字串。"""
        path = os.path.join(self.ws, rel)
        try:
            text = cc.read_text(path)
        except OSError:
            return ""
        lang = cc.language_of(path)
        try:
            items = repo_map_cmd.outline_for(path, text, lang) if lang in cc.CODE_LANGS else []
        except Exception:   # noqa: BLE001  大綱只是提示，失敗不影響工具結果
            return ""
        names = [t for _, t in items[:limit]]
        return "、".join(names) + ("…" if len(items) > limit else "")

    def _after_tool(self, script, args, mode, status, out):
        """工具結果的補充：(1) 記下這個檔案該看的位置（code_view 的範圍、SEARCH 對不上時最像的段落），之後的修改視窗以它為中心；
        (2) 寫入成功後附上檔案現在有哪些類別與函式——決策 session 看不到內容通道寫了什麼，實測 Qwen 建立檔案時就把整個功能寫完，
        worker 接著又要「實作某函式」，內容通道原樣送回（DevBench 三次 52～63 次空轉、佔 11～16% 的呼叫）；
        (3) 空轉（新內容跟檔案一樣）時明說檔案裡已經有哪些，讓它直接回報完成。"""
        paths = [a for a in args if not a.startswith("--")]
        if not paths:
            return out
        rel = os.path.relpath(os.path.realpath(os.path.join(self.ws, paths[0])), self.ws)
        if script == "code_view_cmd.py" and status == "PASS":
            m = _VIEW_RANGE_RE.search(out.split("\n", 1)[0])
            if m:
                self.focus[rel] = (int(m.group(1)), int(m.group(2)))
        elif script == "code_edit_cmd.py" and status == "ERROR":
            m = _CLOSEST_RE.search(out)
            if m:
                self.focus[rel] = (int(m.group(1)), int(m.group(2)))
        if script not in CODING_PAYLOAD_SCRIPTS or not mode:
            return out
        if status == "PASS":
            names = self._outline_names(rel)
            return out + (f"\n（{rel} 現在有：{names}）" if names else "")
        if "新內容跟檔案目前的內容完全一樣" in out:
            names = self._outline_names(rel)
            if names:
                out += (f"\n（{rel} 目前已經有：{names}。這一步要做的如果已經在裡面，就不要再改了：回報完成（action 填 null）；"
                        f"要改的是其中某個函式的內容，先 code_view {rel} --symbol 名稱 看實際的程式。）")
        return out

    # ---------------------------------------------------------------- 驗證
    def _changed_files(self):
        """這一項改過的檔案：這個 worker 改的，加上這一項之前的嘗試（上一個 worker）改過的。不算其他項目改的同一個檔案：
        不然第 2 項的檔案只要第 1 項改過，worker 什麼都沒做也會被當成「改過」，跳過「還沒修改就回報完成」的提醒。"""
        out = list(dict.fromkeys(self.edited + list(self.item.get("changed") or [])))
        return [r for r in out if os.path.exists(os.path.join(self.ws, r))]

    _COV_ROW = re.compile(r"^(?P<file>[^｜\n]+)｜(?P<pct>[\d.]+)%（(?P<cov>\d+)/(?P<tot>\d+)）｜(?P<br>[^｜\n]*)｜(?P<miss>.*)$", re.M)

    def _target_sources(self):
        """這一項要測的正式程式：標題與 goal 裡提到的工作區檔案；都沒提到才用 context_files 裡的非測試檔。
        context_files 常是參考用的依賴（實測：「為 utils 寫測試」的項目附了 result.py 當參考，覆蓋率檢查就逼 worker 去測 result.py，
        跟下一項重複、還因為驗證沒過換了一次 worker）。"""
        goal = f"{self.item.get('title', '')} {self.item.get('goal', '')}"
        files = [rel for rel in self._ws_files()
                 if not cc.is_test_path(rel) and (rel in goal or (os.path.basename(rel) in goal and len(os.path.basename(rel)) > 4))]
        if not files:
            files = [f for f in (self.item.get("context_files") or []) if not cc.is_test_path(f)]
        return list(dict.fromkeys(files))

    def _coverage_check(self, test_files):
        """只寫測試的工作：這一項的測試通過後量覆蓋率；目標程式的行覆蓋率低於 CODING_COVERAGE_TARGET 時把沒測到的行交還 worker
        （最多 CODING_COVERAGE_ROUNDS 次）。回傳 (通過, 說明)。"""
        out = self.o.run_script(self.job, "code_test_cmd.py", test_files + ["--coverage", "--timeout", str(CODING_RUN_TIMEOUT)],
                                timeout=CODING_RUN_TIMEOUT + 30)
        rows = {m["file"].strip(): m for m in self._COV_ROW.finditer(out)}
        if not rows:
            sect = re.search(r"── 覆蓋率[^\n]*", out)
            return True, f"（覆蓋率：{sect.group(0) if sect else '沒有量到'}）"
        targets = [t for t in self._target_sources() if t in rows]
        low = [(t, rows[t]) for t in targets if int(rows[t]["tot"]) > 0 and float(rows[t]["pct"]) < CODING_COVERAGE_TARGET]
        summary = "；".join(f"{t} {rows[t]['pct']}%" for t in targets) or "、".join(f"{f} {m['pct']}%" for f, m in list(rows.items())[:6])
        if low and self.coverage_rounds < CODING_COVERAGE_ROUNDS:
            self.coverage_rounds += 1
            lines = "\n".join(f"- {t}：行覆蓋率 {m['pct']}%（{m['cov']}/{m['tot']}），還沒測到：{m['miss'].strip()}" for t, m in low)
            return False, (f"[ERROR] 測試都通過了，但被測的程式還有沒測到的部分（目標：行覆蓋率 {CODING_COVERAGE_TARGET:.0f}% 以上）：\n{lines}\n"
                           f"先用 code_view 看那幾行在做什麼，再在 {'、'.join(test_files)} 補測試涵蓋它們（正常、邊界、錯誤處理的分支；"
                           f"用斷言檢查結果）。真的測不到的（例如只在 __main__ 執行、需要網路或硬體），就回報完成並在摘要說明原因。")
        return True, f"（覆蓋率：{summary}）"

    def verify(self):
        """回傳 (通過, 說明文字)。靜態檢查改過的檔案，再跑這一項的驗證指令。"""
        parts, ok = [], True
        changed = self._changed_files()
        if changed:
            # 任務附了規格文件（例如 PRD、UML、架構設計）時，順便對照規格裡的函式簽名（參數個數）
            spec = [a for rel in self.o.task_document_paths(self.job) if rel.endswith((".md", ".rst"))
                    for a in ("--spec", rel)]
            out = self.o.run_script(self.job, "code_check_cmd.py", changed + spec)
            parts.append(out)
            ok = ok and not out.lstrip().startswith("[ERROR]")
        cmd = (self.item.get("verify") or "").strip()
        if cmd and ok:
            out = self.o.run_verify_command(self.job, cmd)
            head = out.split("\n", 1)[0]
            missing = re.match(r"\[ERROR\] 找不到測試路徑：(\S+)", head)
            if missing and missing.group(1).split("::")[0] not in (self.item.get("files") or []):
                # 驗證指令要跑的測試檔不存在、也不是這一項要建立的（計畫寫錯）：跟「還沒有測試」一樣先略過，不逼 worker 去寫
                parts.append(f"（驗證指令「{cmd}」要跑的 {missing.group(1)} 不存在、也不是這一項要建立的檔案，這一項先略過；"
                             f"整體驗證時會再跑全部測試）")
            elif "沒有收集到任何測試" in head:
                # 計畫常拿「後面的項目才會寫的測試」來驗證前面的項目：測試還不存在不算失敗，整體驗證時會再跑全部測試。
                # 但這一項自己就要寫測試、卻一個都沒收集到，就是沒寫好。
                files = self.item.get("files") or []
                writes_tests = any(re.search(r"(^|/)(test_[^/]*|[^/]*_test)\.py$", f) or cpp.is_test_source(f) for f in files)
                if writes_tests:
                    parts.append(out + "\n（這一項要寫的測試沒有被收集到：Python 測試檔名要是 test_*.py、測試函式名稱要以 test 開頭；"
                                       "C／C++ 用 gtest 的 TEST(套件, 名稱)，檔案放 tests／ 或叫 test_*.cpp，有 CMakeLists.txt 時要註冊測試）")
                    ok = False
                elif (self.job.get("baseline") or {}).get("cases"):
                    # 專案本來就有測試，驗證指令卻一個都沒跑到（標籤或路徑寫錯）：不能算通過，改用整個專案的測試做回歸檢查（下面）
                    parts.append(f"（驗證指令「{cmd}」沒有跑到任何測試：{head[:160]}；改用整個專案的測試做回歸檢查）")
                else:
                    parts.append(f"（驗證指令「{cmd}」目前還沒有可以跑的測試，這一項先略過；整體驗證時會再跑全部測試）")
            elif "沒辦法在這台主機跑這些測試" in head:
                # 測試全部需要這台主機沒有的外部依賴（沒有 ROS 2 時的 rclpy、rclcpp、ament_flake8…）：不是程式的錯，
                # 改程式也不會好——這一項以前面的靜態檢查為準，不逼 worker 去「修」
                parts.append(out + "\n（這些測試需要這台主機沒有的外部依賴，沒辦法在這裡跑；這一項以靜態檢查為準。"
                                   "不要為了這個改程式、改 #include 或安裝套件）")
            else:
                parts.append(out)
                ok = ok and not out.lstrip().startswith("[ERROR]")
        test_files = [f for f in changed if cc.is_test_path(f) and (f.endswith(".py") or cpp.is_test_source(f))]
        if ok and test_files:
            bare = [f"{f}：{n}" for f in test_files for n in cc.tests_without_assertions(os.path.join(self.ws, f))]
            if bare:
                ok = False
                parts.append("[ERROR] 這些測試沒有任何斷言（只呼叫函式、沒有檢查結果，抓不到錯誤）：" + "、".join(bare[:12])
                             + "\n請加上斷言：Python 用 assert 比對回傳值與狀態、pytest.raises 檢查例外；C++ 用 EXPECT_EQ／EXPECT_TRUE／"
                               "EXPECT_THROW 之類。")
        if ok and test_files and self.job.get("tests_only"):
            cov_ok, cov_text = self._coverage_check(test_files)
            parts.append(cov_text)
            ok = ok and cov_ok
        if ok and changed and (self.job.get("baseline") or {}).get("cases"):
            # 回歸檢查：開工前通過的測試，這一項做完之後還要通過（只跑這一項的驗證指令抓不到改壞別的地方）
            broken, now, sout = self.o.regressions(self.job)
            if broken:
                ok = False
                parts.append(self.o.regression_text(broken, now, sout))
            elif broken is not None:
                parts.append(f"（回歸檢查：開工前通過的測試都還通過；目前 {sum(1 for v in now.values() if v == 'passed')} 個通過、"
                             f"{sum(1 for v in now.values() if v == 'failed')} 個失敗）")
        if not parts:
            parts.append("（這一項沒有改到檔案，也沒有驗證指令）")
        return ok, "\n\n".join(parts)

    # ---------------------------------------------------------------- 上下文
    def _ctx_chars(self):
        return sum(len(m["content"]) for m in self.messages)

    def _compact(self):
        """上下文超過 num_ctx × CODING_WORKER_CTX_RATIO：最近幾則以外的工具回傳換成一行摘要（原文在 worker 紀錄檔）。"""
        limit = NUM_CTX * CODING_WORKER_CTX_RATIO * self.agent.chars_per_token
        if self._ctx_chars() <= limit:
            return
        idxs = [i for i, m in enumerate(self.messages) if m["role"] == "user" and m["content"].startswith("[tool result]")]
        for i in idxs[:-_KEEP_RECENT_RESULTS]:
            content = self.messages[i]["content"]
            if "（已省略" in content[:200]:
                continue
            head = content.split("\n")[1] if "\n" in content else content
            self.messages[i] = {"role": "user", "content": f"[tool result]（已省略較舊的回傳以節省空間；第一行是：{head[:200]}）"}
            if self._ctx_chars() <= limit * 0.8:
                break

    def _tool_message(self, command, out):
        return {"role": "user", "content": f"[tool result] {command}\n{cc.clip_middle(out, CODING_TOOL_RESULT_MAX_CHARS, '工具回傳')}"}

    # ---------------------------------------------------------------- 主迴圈
    def run(self):
        """回傳 {status: done|failed|cancelled, summary, changed, steps, failure, verify}。"""
        brief = self._brief()
        self.messages = [{"role": "system", "content": self._system()}, {"role": "user", "content": brief}]
        self._log("任務說明", brief)
        verify_rounds, no_change_nudged, last_verify = 0, False, ""
        try:
            while self.steps < CODING_WORKER_MAX_STEPS:
                self.o.wait_if_paused(self.job)
                if self.o.cancel_requested(self.job):
                    return self._result("cancelled", "使用者停止了 job")
                self.steps += 1
                self.item["steps"] = self.item.get("steps", 0) + 1   # 畫面上即時更新（這一項所有嘗試的總步數）
                raw, parsed = self._decide()
                self.messages.append({"role": "assistant", "content": raw})
                self._log(f"第 {self.steps} 步：worker 的決定", f"```json\n{raw}\n```")
                act = action_text(parsed["action"]) if parsed["action"] else None
                if parsed["reply"]:
                    self.last_reply = parsed["reply"]
                self._emit("step", parsed["reply"] or ("（沒有文字）" if act else "（空白回覆）"),
                           thought=parsed["thought"], action=act, step=self.steps)
                if not parsed["valid"]:
                    self.messages.append({"role": "user", "content": "[harness] 回覆不是合法的 JSON，請只輸出 {thought, reply, action} 這個 JSON。"})
                    continue
                if not parsed["action"]:
                    if not self._changed_files() and (self.item.get("files") or []) and not no_change_nudged:
                        no_change_nudged = True
                        msg = (f"[harness] 你還沒有修改任何檔案，但這一項要處理：{'、'.join(self.item['files'])}。請先用 code_edit／code_write "
                               f"修改，再回報完成；如果確定不需要修改，就在 reply 說明原因、action 再填一次 null。")
                        self.messages.append({"role": "user", "content": msg})
                        self._emit("note", "↩️ worker 沒有改任何檔案就回報完成，請它先修改")
                        continue
                    ok, report = self.verify()
                    last_verify = report
                    self._log("驗證", report)
                    self._emit("verify", "✅ 驗證通過" if ok else "❌ 驗證失敗", ok=ok, detail=cc.clip_middle(report, 4000))
                    if ok:
                        return self._result("done", self.last_reply, verify=report)
                    verify_rounds += 1
                    if verify_rounds >= CODING_VERIFY_ROUNDS:
                        return self._result("failed", f"驗證連續 {verify_rounds} 次沒有通過", verify=report)
                    self.messages.append({"role": "user", "content": (
                        f"[驗證失敗]（第 {verify_rounds} 次，最多 {CODING_VERIFY_ROUNDS} 次）系統驗證你這一項的結果沒有通過：\n"
                        f"{cc.clip_middle(report, CODING_TOOL_RESULT_MAX_CHARS, '驗證輸出')}\n"
                        f"請找出原因並修正（先看錯誤訊息指到的檔案與行號），改好後再回報完成（action 填 null）。")})
                    continue
                out, info = self._run_tool(parsed)
                self._log(f"第 {self.steps} 步：工具回傳（{info['command']}）", f"```\n{out}\n```")
                key = (info["command"], out[:500])
                self._same_count = self._same_count + 1 if key == self._last_action else 0
                self._last_action = key
                if info["status"] == "ERROR":   # 同一個錯誤（同樣的動作、同樣的訊息）不管中間做了什麼，第三次就算卡住
                    self._errors[key] = self._errors.get(key, 0) + 1
                    if self._errors[key] >= 3:
                        self._same_count = 2
                if self._same_count >= 2:
                    # 同樣的動作連續三次得到同樣的結果：小模型在這種狀態下幾乎不會自己跳出來（實測一直重送同一份檔案內容），
                    # 提早結束這個 worker，讓新的 worker（乾淨的上下文、帶著失敗原因）或使用者接手，不把步數耗完
                    self._emit("tool", out.split("\n", 1)[0][:300], command=info["command"], status=info["status"],
                               detail=cc.clip_middle(out, 5000), step=self.steps)
                    self._emit("note", "⛔ 同樣的動作已經 3 次得到同樣的結果，這個 worker 卡住了，提早結束")
                    return self._result("failed", f"卡住了：「{info['command']}」已經 3 次得到同樣的結果",
                                        verify=last_verify or out)
                if self._same_count >= 1:
                    out += ("\n（你已經用同樣的動作得到同樣的結果了：不要再重複，換一個做法——例如先 code_view 看實際內容、"
                            "改用別的檔案或參數，或這一項已經完成就回報完成。再重複一次這個 worker 就會被結束。）")
                self._emit("tool", out.split("\n", 1)[0][:300], command=info["command"], status=info["status"],
                           detail=cc.clip_middle(out, 5000), step=self.steps)
                self.messages.append(self._tool_message(info["command"], out))
                self._compact()
            ok, report = self.verify()
            if ok and self._changed_files():
                self._emit("verify", "✅ 步數用完，但驗證通過", ok=True, detail=cc.clip_middle(report, 4000))
                return self._result("done", self.last_reply or "（步數用完時驗證通過）", verify=report)
            return self._result("failed", f"用完 {CODING_WORKER_MAX_STEPS} 步還沒有完成", verify=report or last_verify)
        except _Cancelled:
            return self._result("cancelled", "使用者停止了 job")
        except Exception as e:
            self._log("錯誤", repr(e))
            return self._result("failed", f"worker 發生錯誤：{e}")

    def _result(self, status, summary, verify=""):
        changed = self._changed_files()
        failure = ""
        if status == "failed":
            tail = [m["content"] for m in self.messages[-6:] if m["role"] == "user"]
            failure = f"{summary}。\n最後的驗證或工具回傳：\n{cc.clip_middle(verify or (tail[-1] if tail else ''), 3000)}"
        self._log("結果", json.dumps({"status": status, "summary": summary, "changed": changed}, ensure_ascii=False))
        return {"status": status, "summary": summary, "changed": changed, "steps": self.steps, "calls": self.calls,
                "failure": failure, "verify": verify}


class _Cancelled(Exception):
    pass
