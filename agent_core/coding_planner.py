"""CodingPlannerMixin：coding job 的規劃——探索專案、挑要先讀的檔案（scout）、拆成 work items（plan）、用說的修改計畫（只套用操作）。

規劃跟 /plan（plan.py）同一個原則：計畫是 harness 保存的資料，模型只負責提出內容或「要套用的操作」，不重寫整份；
每一次都是一次性的獨立 session（format= 強制結構），不碰主對話。專案地圖由 repo_map 腳本算（檔案、行數、類別與函式、
測試指令），模型不必自己探索就知道專案長什麼樣子；scout 再讓它挑幾個檔案看完整內容，plan 才有根據寫出具體的 goal。
規劃 session 的 system prompt 是 coding_agents/planner.md（可以直接改），每一步的規則接在後面。
"""
import json
import os
import re
import shlex
import shutil
from skills_system.scripts import _code_common as cc
from skills_system.scripts import _cpp_common as cpp
from skills_system.scripts import repo_map_cmd
from .config import (
    CODING_FILE_PREVIEW_MAX_LINES,
    CODING_MAP_MAX_CHARS,
    CODING_MAX_ITEMS,
    CODING_SCOUT_MAX_FILES,
    NUM_CTX,
)
from .schemas import CODE_PLAN_OPS_SCHEMA, CODE_PLAN_SCHEMA, CODE_SCOUT_SCHEMA

_VERIFY_ONLY_RE = re.compile(r"(final\s*verif|verification|驗證|執行(全部|所有)?測試|跑(全部|所有)?測試|run\s+(all\s+)?tests|確認.*(通過|正確))", re.I)
_SCOUT_RULES = (
    "【這一步：挑出規劃前要先看完整內容的檔案】\n"
    f"files_to_read：最多 {CODING_SCOUT_MAX_FILES} 個，路徑照專案地圖抄（相對路徑）。挑會被修改的檔案、它們呼叫或被呼叫的檔案、"
    "相關的測試；跟任務無關的不要挑。\n"
    "understanding：兩三句寫你理解的任務（要做什麼、大概會動到哪裡）。\n"
    "questions：任務裡需要使用者決定、你沒辦法自己判斷的地方（沒有就給空陣列，不要為了問而問）。只輸出 JSON。")
_TESTS_ONLY_NOTE = ("\n\n【這是只寫測試的工作】正式程式不能修改（worker 也改不了）。每一項寫一個（或一組相關的）模組的測試："
                    "files 只列測試檔（例如 unit_tests/test_utils.py、tests/test_parser.cpp），被測的正式程式放 context_files；"
                    "verify 跑那個測試檔。goal 寫清楚要測哪些公開類別／函式、要涵蓋的情況（正常、邊界、錯誤處理），"
                    "斷言要檢查回傳值與副作用。不要安排「量覆蓋率」「確認環境」這種項目：每一項的測試通過後 harness 會自動量覆蓋率，"
                    "整體驗證也會附上整個專案的覆蓋率。")


_PLAN_RULES = (
    "【這一步：寫出計畫】\n"
    "依照專案地圖與檔案內容，把任務拆成 work items（欄位與原則見上面）。\n"
    "summary：兩三句說明整體做法。\n"
    "final_verify：全部做完後的整體驗證指令。專案的開發規範（AGENTS.md、.coding_agent.md…）寫了怎麼跑測試，就一律照它；否則用專案地圖"
    "「建議的測試指令」（例如 python3 -m pytest -q 或 code_test；帶 <…> 的要換成實際的測試模組或檔案）。測試很多的大型專案不要跑全部測試："
    "寫跟這次修改有關的測試（測試模組、測試檔），或給空字串（系統會依序跑每一項的驗證指令）。沒有測試就給空字串。\n"
    "risks：可能出問題、需要使用者留意的地方（沒有就空陣列）。\n"
    f"最多 {CODING_MAX_ITEMS} 項。只輸出 JSON。")
_REVISE_RULES = (
    "【這一步：照使用者的意見修改計畫】\n"
    "你會收到目前的計畫（有編號）與使用者的修改意見。只輸出要套用在計畫上的操作，不要重寫整份，使用者沒提到的項目不要動。\n"
    "操作：add（加在最後）、insert（插在第 step 項之前）、edit（改第 step 項）、delete（刪第 step 項）、move（把第 step 項移到第 to 項）。"
    "step／to 一律用目前計畫上的編號（從 1 開始）；用不到的欄位給 0、空字串或空陣列；edit 時沒有要改的欄位照抄原本的內容。\n"
    "final_verify：使用者要改整體驗證指令時才填新的，否則照抄目前的。只輸出 JSON。")


def _full_paths(text, files):
    """goal／標題寫的是套件裡的相對路徑（「在 test/test_battery.py 加測試」）、計畫的檔案是完整路徑
    （src/amr_tools/test/test_battery.py）時，換成完整路徑：worker 照 goal 的路徑做，實測 e4b 會在工作區根目錄另外建一個。"""
    for f in sorted(files, key=len, reverse=True):
        parts = f.split("/")
        for k in range(1, len(parts) - 1):
            text = re.sub(rf"(?<![\w./-]){re.escape('/'.join(parts[k:]))}(?![\w-])", f, text)
    return text


_PLACEHOLDER_RE = re.compile(r"<[^<>\s]*[\u4e00-\u9fff][^<>]*>|<(?:test|tests|module|file|path|name)[^<>]*>", re.I)
_TEST_COUNT_RE = re.compile(r"測試檔 (\d+) 個")


class CodingPlannerMixin:

    # ---------------------------------------------------------------- 共用
    def prompt_file(self, name):
        path = os.path.join(self.agent.script_dir, "coding_agents", name)
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def _planner_chat(self, job, kind, rules, user_prompt, schema):
        """一次性的規劃 session：回傳 (dict 或 None, 錯誤文字)。"""
        system = self.prompt_file("planner.md").replace("{max_items}", str(CODING_MAX_ITEMS)) + "\n\n" + rules
        job["model_calls"] = job.get("model_calls", 0) + 1
        try:
            res = self.agent._timed_chat(
                kind, model=self.planner_model(), format=schema, think=self.think_for("planner"),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
                options={"temperature": 0.2, "num_ctx": NUM_CTX},
            )
        except Exception as e:
            return None, f"規劃 session 呼叫模型失敗：{e}"
        try:
            data = json.loads(res["message"]["content"])
            return (data, None) if isinstance(data, dict) else (None, "規劃 session 的回覆不是 JSON 物件")
        except (ValueError, TypeError):
            return None, "規劃 session 的回覆不是合法的 JSON"

    def outline_of(self, path, text):
        """單一檔案的結構大綱（Python 用 AST，其他語言用 repo_map 的正規表示式），沒有可列的就給前 40 行。"""
        lang = cc.language_of(path)
        items = repo_map_cmd.outline_for(path, text, lang) if lang in cc.CODE_LANGS else []
        if items:
            return "\n".join(f"  {'  ' * d}{t}" for d, t in items)
        lines = text.split("\n")[:40]
        return f"```{cc.fence_lang(path)}\n" + "\n".join(lines) + "\n```"

    def task_document_paths(self, job):
        """任務文字裡提到、工作區裡真的有的文件（.md／.txt／.rst）的相對路徑，依提到的順序。"""
        out = []
        for m in re.finditer(r"[\w./-]+\.(?:md|txt|rst)\b", job.get("task") or ""):
            rel = os.path.normpath(m.group(0).lstrip("./"))
            if rel not in out and not rel.startswith("..") and os.path.isfile(os.path.join(job["workspace"], rel)):
                out.append(rel)
        return out

    def task_documents(self, job, budget=16000):
        """任務文字裡提到、工作區裡真的有的文件（.md／.txt／.rst，例如「照 docs/PRD.md 實作」）→ (整份附上的文字, 太長沒附的路徑)。
        規劃與每個 worker、內容通道都附上：規格寫在文件裡的任務（DevBench 這種照 PRD／UML／架構設計實作的），worker 不用自己去讀，
        也不會只靠規劃轉述的片段。依任務裡提到的順序，超過 budget 的文件只列路徑（用 code_view 看）。"""
        ws = job["workspace"]
        blocks, skipped, used = [], [], 0
        for rel in self.task_document_paths(job):
            path = os.path.join(ws, rel)
            try:
                text = cc.read_text(path).strip()
            except OSError:
                continue
            if used + len(text) > budget:
                skipped.append(rel)
                continue
            blocks.append(f"### {rel}\n{text}")
            used += len(text)
        return "\n\n".join(blocks), skipped

    # ---------------------------------------------------------------- 探索
    def explore(self, job):
        """跑 repo_map：回傳 (地圖文字, 建議的測試指令或空字串)。"""
        out = self.run_script(job, "repo_map_cmd.py", [".", "--max-chars", str(CODING_MAP_MAX_CHARS)])
        m = re.search(r"建議的測試指令：([^；\n）]+)", out)
        n = _TEST_COUNT_RE.search(out)
        job["test_files"] = int(n.group(1)) if n else 0     # 整體驗證要不要跑全部測試（coding_job._final_commands）看這個
        return out, (m.group(1).strip() if m else "")

    def read_for_planning(self, job, files):
        """scout 挑的檔案 → 交給 plan 的內容：不長的整份、長的給大綱＋開頭。回傳 (文字, 實際讀到的路徑)。"""
        blocks, used, budget = [], [], 16000
        for rel in files:
            path = os.path.join(job["workspace"], rel)
            if not os.path.isfile(path):
                continue
            try:
                text = cc.read_text(path)
            except OSError:
                continue
            lines = text.split("\n")
            if len(lines) <= CODING_FILE_PREVIEW_MAX_LINES and len(text) <= budget:
                blocks.append(f"### {rel}（{len(lines)} 行）\n```{cc.fence_lang(rel)}\n{text.rstrip()}\n```")
                budget -= len(text)
            else:
                head = "\n".join(lines[:60])
                blocks.append(f"### {rel}（{len(lines)} 行，太長只附結構與開頭）\n{self.outline_of(path, text)}\n"
                              f"開頭：\n```{cc.fence_lang(rel)}\n{head}\n```")
                budget -= len(head) + 400
            used.append(rel)
            if budget <= 0:
                break
        return "\n\n".join(blocks), used

    def symbol_index(self, job):
        """工作區裡 Python 與 C／C++ 檔（測試檔除外）的類別與函式、類別裡的方法 → {名稱: [(相對路徑, 種類, 行號)]}。
        給「goal 提到的名稱定義在哪裡」用：小模型規劃時常把檔案寫錯（實測 e4b 把要改 Inventory 的項目寫成 inventory/models.py，
        Inventory 其實在 inventory/store.py，worker 改了 48 步才由最後的修正 worker 改對）。每次重新掃（worker 可能剛加了新函式）。
        C／C++ 的類別記在定義它的標頭；方法與函式記在有本體的那個檔案（通常是 .cpp），只有宣告時記在標頭。"""
        import ast
        idx = {}
        for full, rel in cc.iter_files(job["workspace"], exts=cpp.ALL_EXTS):
            if cpp.is_test_source(rel):
                continue
            try:
                defs = cpp.definitions(cc.read_text(full))
            except OSError:
                continue
            for name, kind, line in defs:
                idx.setdefault(name, []).append((rel, kind, line))
        for name, entries in list(idx.items()):     # 有本體的定義就不列宣告（同一個名稱只指向一個檔案）
            real = [e for e in entries if e[1] != "decl"]
            idx[name] = real or entries
        for full, rel in cc.iter_files(job["workspace"], exts={".py"}):
            base = os.path.basename(rel)
            if base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py":
                continue
            try:
                tree = ast.parse(cc.read_text(full))
            except (SyntaxError, OSError, ValueError):
                continue
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    idx.setdefault(node.name, []).append((rel, "class", node.lineno))
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("__"):
                            idx.setdefault(f"{node.name}.{sub.name}", []).append((rel, "method", sub.lineno))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    idx.setdefault(node.name, []).append((rel, "def", node.lineno))
        return idx

    def mentioned_symbols(self, job, text, idx=None):
        """文字裡提到、在專案裡有定義的名稱 → [(名稱, 相對路徑, 種類, 行號)]（類別.方法 也認；只取定義在一個檔案的）。"""
        idx = self.symbol_index(job) if idx is None else idx
        out, seen = [], set()
        for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\b", text or ""):
            name = m.group(1)
            for cand in (name, name.split(".")[0], name.split(".")[-1]) if "." in name else (name,):
                defs = idx.get(cand) or []
                if len(defs) == 1 and cand not in seen and len(cand) > 2:
                    seen.add(cand)
                    out.append((cand, *defs[0]))
        return out[:10]

    def _workspace_files(self, job):
        """工作區裡的檔案（相對路徑），規劃期間快取一次。"""
        cache = job.setdefault("_files_cache", None)
        if cache is None:
            cache = [rel for _, rel in cc.iter_files(job["workspace"])]
            job["_files_cache"] = cache
        return cache

    def _clean_path(self, job, raw, must_exist=False, notes=None):
        """模型寫的路徑 → 相對於工作區的乾淨路徑；在工作區外、或 must_exist 卻不存在時回 None。
        小模型常把目錄前綴弄丟（實測 e4b 把 inventory/store.py 寫成 store.py，worker 就在根目錄建了一個新的 store.py）：
        寫的路徑不存在、但專案裡剛好只有一個同名（或結尾相同）的檔案時，改成那個檔案，並在 notes 記一筆提醒。"""
        p = str(raw or "").strip().strip("`'\"").replace("\\", "/")
        p = re.sub(r"^\./", "", p)
        if not p or p in (".", "/"):
            return None
        ws = job["workspace"]
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(ws, p))
        if not (full == ws or full.startswith(ws.rstrip(os.sep) + os.sep)):
            return None
        rel = os.path.relpath(full, ws)
        if os.path.isdir(full):
            return None
        if not os.path.exists(full):
            files = self._workspace_files(job)
            cands = [f for f in files if f.endswith("/" + rel)] or \
                [f for f in files if os.path.basename(f) == os.path.basename(rel)]
            if len(cands) == 1:
                if notes is not None:
                    notes.append(f"路徑「{rel}」不存在，改成專案裡實際的 {cands[0]}")
                return cands[0]
            if must_exist:
                return None
        return rel

    def _clean_verify(self, cmd):
        """驗證指令：python 換成這台機器有的 python3；scripts/code_test_cmd.py 寫成 code_test；不能執行的（被安全檢查擋下）
        回 (空字串, 原因)。"""
        cmd = " ".join(str(cmd or "").split())
        if not cmd:
            return "", None
        if cmd.lower() in ("無", "none", "n/a", "-", "null"):
            return "", None
        cmd = re.sub(r"^(?:EXECUTE:\s*)?(?:python3?\s+)?(?:\S*/)?code_test(?:_cmd\.py)?\b", "code_test", cmd)
        if _PLACEHOLDER_RE.search(cmd):
            # 專案地圖的建議指令帶佔位符（python3 tests/runtests.py <測試模組>）：照抄的話 bash 會把 < 當成輸入轉向
            return "", f"指令裡還有沒換掉的佔位符（{_PLACEHOLDER_RE.search(cmd).group(0)}）"
        if shutil.which("python") is None:
            cmd = re.sub(r"(^|&&\s*|;\s*)python(\s)", r"\1python3\2", cmd)
        blocked = cc.check_command(cmd)
        if blocked:
            return "", blocked
        return cmd, None

    def _drop_missing_test_paths(self, job, verify, will_exist):
        """驗證指令（code_test／pytest）要跑的測試路徑既不存在、前面的項目與這一項也不會建立時拿掉——不然 worker 只會看到
        「找不到測試路徑」，為了通過驗證去寫任務沒有要求的測試（實測 DevBench 的任務明說不用寫測試，計畫卻寫
        code_test tests/test_shape.cpp）。回傳 (新的指令, 拿掉的路徑 list)；拿掉後沒有東西可以跑就回空字串。"""
        m = re.match(r"^(code_test|(?:\S*/)?python3?\s+-m\s+pytest|pytest)\b(.*)$", verify)
        if not m or re.search(r"[;&|<>`$]", verify):
            return verify, []
        try:
            args = shlex.split(m.group(2))
        except ValueError:
            return verify, []
        keep, dropped, targets, i = [], [], 0, 0
        while i < len(args):
            a = args[i]
            if a.startswith("-"):
                keep.append(a)
                if a in ("-k", "-m", "--timeout", "--lang") and i + 1 < len(args):
                    keep.append(args[i + 1])
                    i += 1
            else:
                rel = os.path.normpath(a.split("::")[0])
                if os.path.exists(os.path.join(job["workspace"], rel)) or rel in will_exist or \
                        any(f.startswith(rel.rstrip("/") + "/") for f in will_exist):
                    keep.append(a)
                    targets += 1
                else:
                    dropped.append(a)
            i += 1
        if not dropped:
            return verify, []
        if not targets:
            return "", dropped
        return " ".join([m.group(1)] + [shlex.quote(k) for k in keep]), dropped

    _STD_MODULES = {"pytest", "unittest", "http", "json", "venv", "pip", "doctest", "timeit", "cProfile", "pdb", "trace",
                    "compileall", "py_compile", "zipfile", "tarfile", "base64", "calendar", "site", "this", "webbrowser"}

    def _missing_module(self, job, verify, will_exist):
        """驗證指令裡 python3 -m <模組> 的模組不在工作區、計畫也不會建立時回傳模組名稱（標準庫與 pytest 這類不算）。"""
        m = re.search(r"(?:^|[\s;&|])(?:\S*/)?python3?(?:\.\d+)?\s+-m\s+([A-Za-z_][\w.]*)", verify or "")
        if not m:
            return None
        top = m.group(1).split(".")[0]
        if top in self._STD_MODULES:
            return None
        ws = job["workspace"]
        if os.path.isdir(os.path.join(ws, top)) or os.path.isfile(os.path.join(ws, top + ".py")):
            return None
        if any(f == top + ".py" or f.startswith(top + "/") for f in will_exist):
            return None
        import importlib.util
        if importlib.util.find_spec(top) is not None:     # 裝好的第三方套件（例如 python3 -m http.server、flask）
            return None
        return m.group(1)

    def declared_new_files(self, job):
        """任務文字裡列出、工作區裡還沒有的檔案（例如「要寫的檔案：1. src/a.cpp 2. include/a.h …」）。"""
        out = []
        for m in re.finditer(r"(?<![\w/.-])((?:[\w.-]+/)*(?:[\w-]+\.[A-Za-z0-9+]{1,5}|[Mm]akefile|CMakeLists\.txt))(?![\w/])",
                             job.get("task") or ""):
            rel = os.path.normpath(m.group(1))
            if rel not in out and not os.path.exists(os.path.join(job["workspace"], rel)) and not rel.endswith((".md", ".txt", ".rst")):
                out.append(rel)
        return out

    def listed_new_files(self, job):
        """任務文字裡「一行一個」列出、工作區還沒有的檔案（例如「1. src/a.cpp」「- include/a.h」），依列出的順序。
        跟 declared_new_files 不同：散在句子裡的檔名（「例如套件的 __init__.py」）不算。"""
        out = []
        for m in re.finditer(r"^\s*(?:\d+[.)、]|[-*•])\s*`?((?:[\w.-]+/)*(?:[\w-]+\.[A-Za-z0-9+]{1,5}|[Mm]akefile|CMakeLists\.txt))`?\s*$",
                             job.get("task") or "", re.M):
            rel = os.path.normpath(m.group(1))
            if rel not in out and not os.path.exists(os.path.join(job["workspace"], rel)):
                out.append(rel)
        return out

    def cover_listed_files(self, job, items, warns):
        """計畫漏掉任務清單列出的檔案時，依清單的順序補上「照規格實作這個檔案」的項目。實測 e4b 照 DevBench 的 hone 規劃時，
        任務列了 4 個要寫的檔案，計畫只有 1 項（CSVUtils），job 顯示「完成」但另外 3 個檔案根本沒寫。"""
        listed = self.listed_new_files(job)
        if len(listed) < 2:
            return items
        planned = {f for it in items for f in it["files"]}
        missing = [f for f in listed if f not in planned]
        if not missing:
            return items
        for f in missing[:max(0, CODING_MAX_ITEMS - len(items))]:
            goal = (f"實作 {f}：任務列出了這個檔案，計畫原本漏掉了。照任務與規格文件（說明裡已附上）寫出這個檔案的完整內容——"
                    f"類別、函式、參數、回傳值與輸出格式照文件，用到其他檔案的東西時照那些檔案目前的實際名稱。")
            items.append(self.new_item(len(items) + 1, f"實作 {os.path.basename(f)}", goal, [f], [], ""))
        warns.append(f"計畫漏了任務列出的檔案：{'、'.join(missing)}，已依清單的順序補上（照規格實作）")
        return items

    def normalize_items(self, job, raw_items, restrict=True):
        """模型給的 items → 乾淨的 work items；回傳 (items, 提醒 list)。restrict：任務一行一個列出要建立的檔案時，
        只准新建那些檔案（過濾後一項都不剩時改成不限制，見最後）。"""
        items, warns = [], []
        sym_idx = self.symbol_index(job)
        will_exist = set()
        dropped_by_list = 0
        # 任務明確列出要新建的檔案（2 個以上）時，計畫只能新建那些檔案（測試檔除外）：實測 e4b 照 DevBench 規格做時，
        # 任務列了 include/Circle.hpp，計畫還是自己多加 src/Circle.cpp，官方的建置檔不編它，測試就連結失敗
        declared = set(self.listed_new_files(job)) if restrict else set()
        allowed_names = set()
        if len(declared) < 2:
            declared = None
        else:
            # 只寫檔名的（「例如套件的 __init__.py」）、任務附的文件裡檔案樹（├── a.py）列出的檔名，也算任務允許的新檔
            allowed_names = {d for d in declared if "/" not in d}
            ws = job["workspace"]
            for rel in self.task_document_paths(job):
                try:
                    text = cc.read_text(os.path.join(ws, rel))
                except OSError:
                    continue
                allowed_names |= set(re.findall(r"[├└]──\s*([\w.+-]+\.[A-Za-z0-9+]{1,5}|[Mm]akefile)\s*$", text, re.M))
        for raw in (raw_items or [])[:CODING_MAX_ITEMS]:
            if not isinstance(raw, dict):
                continue
            title = " ".join(str(raw.get("title") or "").split())[:60]
            goal = str(raw.get("goal") or "").strip()[:900]
            if not (title or goal):
                continue
            files, bad = [], []
            for f in raw.get("files") or []:
                c = self._clean_path(job, f, notes=warns)
                (files if c else bad).append(c or str(f))
            files = list(dict.fromkeys(files))
            title, goal = _full_paths(title, files), _full_paths(goal, files)
            if declared is not None:
                extra = [f for f in files if f not in declared and os.path.basename(f) not in allowed_names
                         and not os.path.exists(os.path.join(job["workspace"], f))
                         and not cpp.is_test_source(f) and not re.search(r"(^|/)(test_[^/]*|[^/]*_test)\.py$", f)]
                if extra:
                    files = [f for f in files if f not in extra]
                    warns.append(f"「{title}」要新建任務沒有列出的檔案 {'、'.join(extra)}，已拿掉（任務列出的新檔案："
                                 f"{'、'.join(sorted(declared))}）" + ("" if files else "；這一項沒有其他檔案，整項拿掉"))
                    if not files:
                        dropped_by_list += 1
                        continue
            ctx = [c for c in (self._clean_path(job, f, must_exist=True, notes=warns) for f in raw.get("context_files") or [])
                   if c and c not in files]
            # goal 提到的類別／函式定義在別的檔案時，把那個檔案加進參考檔案（worker 的任務說明會附上它的結構）
            for name, rel, kind, line in self.mentioned_symbols(job, f"{title} {goal}", sym_idx):
                if rel not in files and rel not in ctx and len(ctx) < 5:
                    ctx.append(rel)
            ctx = list(dict.fromkeys(ctx))
            verify, why = self._clean_verify(raw.get("verify"))
            will_exist |= set(files)
            verify, dropped = self._drop_missing_test_paths(job, verify, will_exist)
            mod = self._missing_module(job, verify, will_exist)
            if mod:   # 實測 e4b 把 planner.md 範例的 python3 -m inventory.cli … 原樣抄進 C++ 專案的計畫
                warns.append(f"「{title}」的驗證指令執行的模組 {mod} 不在這個專案裡、計畫也不會建立，已拿掉：{verify}")
                verify = ""
            if dropped:
                warns.append(f"「{title}」的驗證指令要跑的 {'、'.join(dropped)} 不存在、計畫裡也沒有項目會建立，已拿掉"
                             + ("" if verify else "（這一項改成只做靜態與編譯檢查）"))
            if not files and _VERIFY_ONLY_RE.search(f"{title} {goal[:80]}"):
                # 小模型常在最後加一項「最終驗證／跑全部測試」：沒有要改的檔案，整體驗證本來就會跑，拿掉
                warns.append(f"「{title}」只是執行驗證、沒有要修改的檔案（整體驗證會做），已從計畫拿掉")
                continue
            if bad:
                warns.append(f"「{title}」的檔案路徑不在工作區內，已略過：{'、'.join(bad)}")
            if why:
                warns.append(f"「{title}」的驗證指令不能執行，已拿掉：{why}")
            items.append(self.new_item(len(items) + 1, title or goal[:30], goal or title, files[:6], ctx[:6], verify))
        if restrict and not items and dropped_by_list:
            # 規則把每一項都拿掉了（多半是路徑寫法跟清單不一樣）：寧可不限制，也不要讓整個規劃失敗
            items, more = self.normalize_items(job, raw_items, restrict=False)
            return items, more + ["計畫的檔案都不在任務列出的清單裡，這次不限制新建的檔案（請在核准前確認計畫）"]
        return items, warns

    # ---------------------------------------------------------------- 規劃
    def _tests_only_items(self, job, items, warns):
        """只寫測試的工作：每一項的 files 只留測試檔與建置／測試設定檔，正式程式移到 context_files（看得到、不能改）；
        沒有任何測試檔的項目（例如「量覆蓋率」「確認環境」）拿掉——覆蓋率由整體驗證量。"""
        out = []
        for it in items:
            files = it.get("files") or []
            keep = [f for f in files if cc.is_test_path(f) or cc.BUILD_FILE_RE.search(f)]
            moved = [f for f in files if f not in keep]
            if moved:
                it["context_files"] = list(dict.fromkeys((it.get("context_files") or []) + moved))
                warns.append(f"第 {it['n']} 項：只寫測試的工作不改正式程式，{'、'.join(moved)} 改成參考檔")
            it["files"] = keep
            if not any(cc.is_test_path(f) for f in keep):
                warns.append(f"拿掉第 {it['n']} 項「{it['title']}」：沒有要寫的測試檔（覆蓋率由整體驗證量）")
                continue
            out.append(it)
        for i, it in enumerate(out, 1):
            it["n"] = i
        return out

    def plan_job(self, job):
        """探索 → scout → plan。成功回 True（job 的 items 已填好）；失敗回 False（job['error'] 有原因）。"""
        self.emit(job, "phase", "🔎 探索專案：專案地圖、測試指令")
        repo_map, test_cmd = self.explore(job)
        job["test_cmd"] = test_cmd
        job["tests_only"] = cc.tests_only_task(job["task"])
        if job["tests_only"]:
            self.emit(job, "phase", "🧪 這是只寫測試的工作：每一項只改測試檔、不會修改正式程式；每一項的測試通過後會量覆蓋率，"
                                    "沒測到的行交還 worker 補測試；整體驗證會附上覆蓋率")
        head = repo_map.split("\n", 2)
        self.emit(job, "phase", "🗺️ " + (head[0][7:] if head[0].startswith("[PASS]") else head[0])[:200],
                  detail=cc.clip_middle(repo_map, 6000))
        rules_name, rules = self.project_rules(job)
        docs, docs_skipped = self.task_documents(job)
        base = (f"【任務】\n{job['task']}\n\n【工作區（專案根目錄）】{job['workspace']}\n\n【專案地圖】\n{repo_map}"
                + (f"\n\n【建議的測試指令】{test_cmd}" if test_cmd else "\n\n【測試】專案裡還沒有測試檔")
                + (f"\n\n【專案的開發規範（{rules_name}，要遵守）】\n{rules}" if rules else "")
                + (f"\n\n【任務提到的文件（規格，整份附上；每個 worker 也會拿到）】\n{docs}" if docs else "")
                + (f"\n\n（任務提到、但太長沒有附上的文件：{'、'.join(docs_skipped)}）" if docs_skipped else "")
                + (_TESTS_ONLY_NOTE if job.get("tests_only") else ""))
        if docs:
            shown = [p for p in self.task_document_paths(job) if p not in docs_skipped]
            self.emit(job, "phase", f"📄 任務提到的文件整份附給規劃與每個 worker：{'、'.join(shown)}")
        if rules:
            self.emit(job, "phase", f"📏 讀到專案的開發規範 {rules_name}：規劃與每個 worker 都會照著做")
        self.emit(job, "phase", f"🧭 規劃 session（{self.planner_model()}）：挑出要先看的檔案")
        scout, err = self._planner_chat(job, "code_scout", _SCOUT_RULES, base, CODE_SCOUT_SCHEMA)
        files = []
        if scout:
            files = [c for c in (self._clean_path(job, f, must_exist=True) for f in scout.get("files_to_read") or []) if c]
            job["_files_cache"] = None
            job["understanding"] = str(scout.get("understanding") or "").strip()
            job["questions"] = [str(q).strip() for q in scout.get("questions") or [] if str(q).strip()]
        else:
            self.emit(job, "error", f"⚠️ {err}；改成直接規劃")
        files = list(dict.fromkeys(files))[:CODING_SCOUT_MAX_FILES]
        file_text, used = self.read_for_planning(job, files)
        if used:
            self.emit(job, "phase", f"📖 讀了 {len(used)} 個檔案：{'、'.join(used)}")
        user = base + (f"\n\n【你對任務的理解】{job.get('understanding')}" if job.get("understanding") else "") \
            + (f"\n\n【檔案內容】\n{file_text}" if file_text else "")
        self.emit(job, "phase", f"📝 規劃 session（{self.planner_model()}）：拆成 work items")
        plan, err = self._planner_chat(job, "code_plan", _PLAN_RULES, user, CODE_PLAN_SCHEMA)
        if not plan:
            job["error"] = err or "規劃 session 沒有給出計畫"
            return False
        items, warns = self.normalize_items(job, plan.get("items"))
        items = self.cover_listed_files(job, items, warns) if items else items
        if not items:
            job["error"] = ("規劃 session 沒有給出任何可以執行的 work item（可以換較大的規劃模型：/code_model planner gemma4:26b）"
                            + (f"；規劃的提醒：{'；'.join(warns)}" if warns else
                               f"；規劃回了 {len(plan.get('items') or [])} 項，都沒有標題與內容"))
            return False
        if job.get("tests_only"):
            items = self._tests_only_items(job, items, warns)
            if not items:
                job["error"] = "只寫測試的工作，計畫裡沒有任何要寫的測試檔" + (f"；{'；'.join(warns)}" if warns else "")
                return False
        job["items"] = items
        job["summary"] = str(plan.get("summary") or "").strip()
        job["risks"] = [str(r).strip() for r in plan.get("risks") or [] if str(r).strip()]
        fv, why = self._clean_verify(plan.get("final_verify"))
        job["final_verify"] = fv or re.sub(r"\s*<[^<>]+>", "", test_cmd).strip()
        if job.get("tests_only"):
            job["final_verify"], why = "code_test --coverage", None      # 跑全部測試並附上覆蓋率（給人審查）
        if why:
            warns.append(f"整體驗證指令不能執行，改用 {test_cmd or '靜態檢查'}：{why}")
        job["warnings"] = warns
        job["_files_cache"] = None
        issues = self.check_plan(job)
        if issues:
            # 用程式檢查計畫、把具體的問題交回規劃 session 改一次（LLM-Modulo 式的 self-refine；不是請模型「再想一次」）
            self.emit(job, "phase", "🔁 計畫檢查發現問題，交回規劃 session 修改一次：" + "；".join(issues))
            note = self.revise_plan_with_feedback(job, "harness 用程式檢查計畫時發現下面的問題，請只修正這些地方（其他項目不要動）：\n"
                                                  + "\n".join(f"- {x}" for x in issues))
            self.emit(job, "phase", f"🔁 規劃 session 的修改：{note}")
            job["plan_revised"] = issues
            left = self.check_plan(job)
            for x in left:
                warns.append(f"計畫檢查（修改後仍然有）：{x}")
        for w in warns:
            self.emit(job, "phase", f"⚠️ {w}")
        return True

    def check_plan(self, job):
        """用程式檢查計畫（小專案才做，試跑驗證指令要時間）：每一項的驗證指令與整體驗證指令實際跑一次——
        「沒有跑到任何測試」「找不到測試路徑」「找不到指令」都是計畫寫錯（評測：django 的測試標籤寫錯、pytest -k 篩不到，
        驗證就變成空的）。這一刻還會失敗的測試（例如要修的 bug）不算問題。回傳問題清單。"""
        if job.get("test_files", 0) >= 50:
            return []
        planned = {f for it in job.get("items") or [] for f in it.get("files") or []}
        cmds = []
        for it in job.get("items") or []:
            c = (it.get("verify") or "").strip()
            if c and c not in [x for _, x in cmds]:
                cmds.append((f"第 {it['n']} 項", c))
        fv = (job.get("final_verify") or "").strip()
        if fv and fv not in [x for _, x in cmds] and not job.get("tests_only"):
            cmds.append(("整體驗證", fv))
        issues = []
        for where, c in cmds[:6]:
            if any(f in c for f in planned if not os.path.exists(os.path.join(job["workspace"], f))):
                continue                         # 驗證的是計畫裡才要建立的檔案：現在跑不到是正常的
            out = self.run_verify_command(job, c)
            head = out.split("\n", 1)[0]
            if "沒有收集到任何測試" in head:
                issues.append(f"{where}的驗證指令「{c}」實際跑一次，一個測試都沒有跑到（{head[:120]}）：測試的路徑、名稱或標籤可能寫錯，"
                              f"請改成會實際跑到相關測試的指令（不確定就用 code_test 加測試檔路徑）")
            elif head.startswith("[ERROR] 找不到測試路徑"):
                issues.append(f"{where}的驗證指令「{c}」要跑的測試不存在（{head[:120]}），也不是計畫裡要建立的檔案")
            elif re.search(r"command not found|No such file or directory|can't open file", out[:2000]) and "[ERROR]" in head:
                issues.append(f"{where}的驗證指令「{c}」跑不起來（{head[:120]}）")
        return issues

    def plan_text(self, job, numbered=True):
        """計畫的純文字（CLI 顯示、修改計畫時交給規劃 session）。"""
        lines = []
        for it in job.get("items") or []:
            mark = {"done": "✅", "failed": "❌", "skipped": "⏭️", "running": "🔄"}.get(it["status"], "⬜") if numbered else ""
            lines.append(f"{it['n']}. {mark} {it['title']}".replace("  ", " "))
            lines.append(f"   要做的事：{it['goal']}")
            if it.get("files"):
                lines.append(f"   檔案：{'、'.join(it['files'])}")
            if it.get("context_files"):
                lines.append(f"   參考：{'、'.join(it['context_files'])}")
            lines.append(f"   驗證：{it.get('verify') or '（靜態檢查）'}")
        lines.append(f"整體驗證：{job.get('final_verify') or '（改過的檔案做靜態檢查）'}")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 修改計畫
    def _apply_op(self, job, op):
        items = job["items"]
        kind = str(op.get("op") or "")
        n, to = int(op.get("step") or 0), int(op.get("to") or 0)
        title = " ".join(str(op.get("title") or "").split())[:60]
        goal = str(op.get("goal") or "").strip()[:900]
        files = [c for c in (self._clean_path(job, f) for f in op.get("files") or []) if c]
        verify, _ = self._clean_verify(op.get("verify"))
        if kind in ("add", "insert"):
            if not (title or goal):
                return f"{kind}：沒有內容，略過"
            if len(items) >= CODING_MAX_ITEMS:
                return f"已經 {CODING_MAX_ITEMS} 項，沒有再加"
            new = self.new_item(0, title or goal[:30], goal or title, files, [], verify)
            if kind == "add" or not 1 <= n <= len(items):
                items.append(new)
            else:
                items.insert(n - 1, new)
            self.renumber(job)
            return f"加入第 {new['n']} 項：{new['title']}"
        if not 1 <= n <= len(items):
            return f"{kind}：沒有第 {n} 項，略過"
        if kind == "edit":
            it = items[n - 1]
            if title:
                it["title"] = title
            if goal:
                it["goal"] = goal
            if files:
                it["files"] = files
            if op.get("verify") is not None and str(op.get("verify")).strip() != "":
                it["verify"] = verify
            return f"修改第 {n} 項：{it['title']}"
        if kind == "delete":
            gone = items.pop(n - 1)
            self.renumber(job)
            return f"刪除第 {n} 項：{gone['title']}"
        if kind == "move":
            if not 1 <= to <= len(items):
                return f"move：沒有第 {to} 項，略過"
            items.insert(to - 1, items.pop(n - 1))
            self.renumber(job)
            return f"第 {n} 項移到第 {to} 項"
        return f"不認得的操作「{kind}」，略過"

    def revise_plan_with_feedback(self, job, feedback):
        """用說的改計畫：規劃 session 只輸出操作，harness 依原本的編號套用（同 plan.py 的做法，避免前面的操作讓編號位移）。
        回傳說明文字。"""
        user = (f"【任務】\n{job['task']}\n\n【目前的計畫】\n{self.plan_text(job, numbered=False)}\n\n"
                f"【使用者的修改意見】\n{feedback}")
        data, err = self._planner_chat(job, "code_revise", _REVISE_RULES, user, CODE_PLAN_OPS_SCHEMA)
        if not data:
            return f"⚠️ {err}；計畫沒有變動（也可以直接在畫面上編輯每一項）。"
        ops = [o for o in data.get("ops") or [] if isinstance(o, dict)]
        original = list(job["items"])
        notes = []
        for o in ops:
            o = dict(o)
            n, to = int(o.get("step") or 0), int(o.get("to") or 0)
            ref = original[n - 1] if 1 <= n <= len(original) else None
            to_ref = original[to - 1] if 1 <= to <= len(original) else None
            if o.get("op") in ("edit", "delete", "move", "insert") and ref is not None:
                if not any(x is ref for x in job["items"]):
                    notes.append(f"{o.get('op')}：原本的第 {n} 項已經不在，略過")
                    continue
                o["step"] = next(i for i, x in enumerate(job["items"]) if x is ref) + 1
            if o.get("op") == "move" and to_ref is not None and any(x is to_ref for x in job["items"]):
                o["to"] = next(i for i, x in enumerate(job["items"]) if x is to_ref) + 1
            notes.append(self._apply_op(job, o))
        fv, _ = self._clean_verify(data.get("final_verify"))
        if fv and fv != job.get("final_verify"):
            job["final_verify"] = fv
            notes.append(f"整體驗證改成：{fv}")
        return "\n".join(f"・{x}" for x in notes) if notes else "規劃 session 沒有提出任何修改（也可以直接在畫面上編輯每一項）。"
