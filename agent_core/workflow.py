"""WorkflowMixin：工作流（skills_system/workflows/<名稱>.md）的執行器——文本當錨點，程式照步驟推進，模型只在判斷點出手。

workflow_run 偽技能（同 task_run：腳本檔只讓存在性檢查與確認關卡照常運作，執行在 harness 的 process 裡）：
    workflow_run <名稱> key=value …     開始（確認關卡列出到第一個【確認】之前會改變狀態的步驟，使用者核准一次）
    workflow_run --continue [<job>]     停在【確認】的工作流接著做（確認關卡：那個【確認】的內容＋接下來會改變狀態的步驟）
    workflow_run --cancel [<job>]       不做了
    workflow_run --list                 列出工作流與需要的資訊

每一步怎麼做（規格見 agent_core/workflow_spec.py）：
- 【執行】參數只用到需要的資訊（與內建的 {today}／{now}）→ 程式直接執行，不經過模型；用到別的佔位符（例：{robot}、{note}）→
  判斷點：交給模型，只填那幾個值（Ollama format＝只有那幾個名稱的 schema），腳本由規格固定、模型換不了；選填的資訊沒給 → 這一步略過。
  做完由程式跑這一步的檢查（輸出有「…」）；技能回 [ERROR] 而且值是模型填的 → 帶著錯誤請模型改一次值再執行，其他的不重試（同樣的命令
  再跑一次結果一樣，會改變狀態的也不能重複做）。
- 【檢查】程式先比對：分支依序，第一個「輸出有這幾個字」成立的就走；都不成立走「其他」；沒有「其他」或沒有分支（關卡）才交給模型選。
- 【確認】停下來：回報停在哪裡、要使用者確認什麼；主對話用 workflow_run --continue 接著做（系統會請使用者確認）。
- 【告知】記下要回報什麼，報告裡列出。
- 最後由程式跑成功判準；「做完了」是程式判斷的，不是模型說的。
存檔：logs/workflow_jobs/<編號>/：job.json（規格、參數、每一步的狀態、輸出的存檔編號、模型填的值與分支）、calls.jsonl（判斷點的模型呼叫：
prompt 與原文回覆）、events.jsonl（進度）。每一步的輸出照常存成 #編號（result_recall 看得到）。"""
import json
import os
import re
import shlex
import time

from . import prompt_files
from . import workflow_spec as ws
from .config import NUM_CTX, WORKFLOW_CONTEXT_CHARS, WORKFLOW_JOBS_DIRNAME, WORKFLOW_JOBS_KEEP
from .jobstore import JobStore

RAW_ARGS_SCRIPTS = {"file_ops_cmd.py"}      # 自己解析 action.args 原文的腳本（HARNESS_RAW_ARGS）：雙引號裡的換行要寫成 \n
_STATUS_TEXT = {"done": "完成", "unverified": "步驟都做了，但成功判準沒過", "ended": "依判斷提早結束", "failed": "沒有完成",
                "paused": "停在【確認】，等使用者", "cancelled": "取消了", "running": "執行中"}
_MARK = {"done": "✅", "skipped": "⏭️", "failed": "❌", "pending": "⬜", "paused": "⏸️"}


def _read_prompt(name):
    """prompts/workflow/<name> 整份（fill.md、check.md：判斷點的規則）。"""
    return prompt_files.load(f"workflow/{name}")


def _w(key, /, **fields):
    """prompts/workflow/inputs.md 的一則：判斷點的 user 訊息裡程式組進去的標籤與選項。"""
    return prompt_files.load("workflow/inputs.md", key, **fields)


def _clip(text, n):
    text = text or ""
    if len(text) <= n:
        return text
    head, tail = text[: n * 2 // 3], text[-n // 3:]
    return f"{head}\n…（中間省略 {len(text) - len(head) - len(tail)} 字；完整的在存檔）…\n{tail}"


def _builtin():
    return {"today": time.strftime("%Y-%m-%d"), "now": time.strftime("%Y-%m-%d %H:%M")}


def _quote_value(value, in_quotes, raw_script):
    """佔位符的值放進命令：在雙引號裡 → 跳脫反斜線與引號（file_ops 這種自己解析原文的，換行也寫成 \\n）；不在引號裡 → shlex.quote。"""
    v = str(value)
    if in_quotes:
        v = v.replace("\\", "\\\\").replace('"', '\\"')
        if raw_script:
            v = v.replace("\r\n", "\n").replace("\n", "\\n").replace("\t", "\\t")
        return v
    return shlex.quote(v) if v and re.search(r"[^\w@%+=:,./~-]", v) else (v or "''")


def fill_template(template, values, script):
    """命令的參數範本 → 實際的參數字串（佔位符換成值；雙引號裡外分開處理）。"""
    out, in_quotes, i = [], False, 0
    raw = script in RAW_ARGS_SCRIPTS
    while i < len(template):
        ch = template[i]
        if ch == '"' and (i == 0 or template[i - 1] != "\\"):
            in_quotes = not in_quotes
            out.append(ch)
            i += 1
            continue
        m = ws.PLACEHOLDER_RE.match(template, i)
        if m and m.group(1) in values:
            out.append(_quote_value(values[m.group(1)], in_quotes, raw))
            i = m.end()
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def subst(text, values):
    """檢查字串、預設值裡的佔位符直接換成值（不加引號；檢查是比對輸出裡的字）。"""
    return ws.PLACEHOLDER_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), text or "")


def _has(output, words):
    low = (output or "").lower()
    return any(w.lower() in low for w in words)


class WorkflowMixin:

    # ---------------------------------------------------------------- 規格
    @property
    def workflows_dir(self):
        return os.path.join(self.base_path, "workflows")

    def _workflow_store(self):
        return JobStore(os.path.join(self.script_dir, "logs", WORKFLOW_JOBS_DIRNAME))

    def load_workflow(self, name):
        """名稱 → 解析好的規格（dict），沒有這個工作流回 None。"""
        name = (name or "").strip()
        name = name[:-3] if name.endswith(".md") else name
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{1,60}", name or ""):
            return None
        path = os.path.join(self.workflows_dir, f"{name}.md")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return ws.parse(f.read(), name, path)

    def list_workflows(self):
        out = []
        if not os.path.isdir(self.workflows_dir):
            return out
        for fn in sorted(os.listdir(self.workflows_dir)):
            if fn.endswith(".md") and not fn.startswith("_"):
                wf = self.load_workflow(fn[:-3])
                if wf:
                    out.append(wf)
        return out

    def _wf_step_changes(self, step):
        """這一步會不會改變狀態：佔位符先換成假的值，交給確認關卡同一套判斷（各腳本自己的解析）。"""
        if step["kind"] != "執行" or not step.get("script"):
            return False
        dummy = {p: "x" for p in ws.placeholders(step.get("args", ""))}
        args = fill_template(step.get("args", ""), dummy, step["script"])
        return bool(self.state_change_info({"action": {"command": f"scripts/{step['script']}", "args": args}}))

    def validate_workflow(self, wf):
        skills = self._script_skill_map()
        return ws.validate(wf, lambda s: os.path.exists(os.path.join(self.base_path, "scripts", s)), lambda s: skills.get(s),
                           self._wf_step_changes)

    # ---------------------------------------------------------------- 參數
    @staticmethod
    def _wf_parse_args(remainder):
        """workflow_run 的參數 → (動作, 名稱或 job, {key: value}, 錯誤)。動作：start／continue／cancel／list。"""
        try:
            toks = shlex.split(remainder or "")
        except ValueError as e:
            return None, None, {}, f"[ERROR] workflow_run 的參數引號不成對（{e}）。下一步：值裡有空白就用雙引號包住，例如 note_file=\"ops notes/a.md\"。"
        if not toks or toks[0] in ("--list", "list"):
            return "list", None, {}, None
        if toks[0] in ("--continue", "continue"):
            return "continue", (toks[1] if len(toks) > 1 else None), {}, None
        if toks[0] in ("--cancel", "cancel"):
            return "cancel", (toks[1] if len(toks) > 1 else None), {}, None
        if toks[0].startswith("-"):
            return None, None, {}, (f"[ERROR] 不認識的選項 {toks[0]}。用法：workflow_run <名稱> key=value …；停在【確認】時 workflow_run --continue；"
                                    f"不做了 workflow_run --cancel；列出全部 workflow_run --list。")
        values, bad = {}, []
        for t in toks[1:]:
            k, sep, v = t.partition("=")
            if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                bad.append(t)
            else:
                values[k] = v
        if bad:
            return None, None, {}, (f"[ERROR] 參數要寫成 名稱=值：{'、'.join(bad)} 看不懂。下一步：照工作流的「需要的資訊」寫，"
                                    f"例如 workflow_run {toks[0]} <名稱>=<值>（名稱照它的「需要的資訊」）。")
        return "start", toks[0], values, None

    def _wf_check_inputs(self, wf, values):
        """使用者給的值 → (完整的值, 錯誤)。必填沒給、多給了不認識的都回錯；選填沒給用預設（預設裡的 {today} 換掉）或空字串。"""
        declared = {i["name"]: i for i in wf["inputs"]}
        unknown = [k for k in values if k not in declared]
        missing = [i["name"] for i in wf["inputs"] if not i["optional"] and not str(values.get(i["name"], "")).strip()]
        usage = "、".join(f"{i['name']}=<{re.sub(r'（.*', '', i['description'])[:20]}>{'（選填）' if i['optional'] else ''}" for i in wf["inputs"])
        if unknown or missing:
            why = "；".join(x for x in (f"不認識的參數：{'、'.join(unknown)}" if unknown else "",
                                        f"少了必填的：{'、'.join(missing)}" if missing else "") if x)
            # 少了必填的有兩種：使用者的需求本來就沒有這一項（例：設定檔沒有分機器人，卻用了改「某一台」的工作流）＝這個工作流不適用；
            # 有這一項但沒說清楚＝問使用者。以前只說「先問使用者」，主對話就去問一個不存在的東西（2026-10-24 fs_edit_param）
            return None, (f"[ERROR] 工作流 {wf['name']} 的參數不對（{why}）。需要的資訊：{usage}。這個工作流是：{wf['description']}。"
                          f"下一步：從使用者的話取得；使用者的需求本來就沒有這一項時，表示不適合用這個工作流，改用技能一步一步做；"
                          f"有這一項只是沒說清楚的，先問使用者，不要用猜的。")
        out = dict(_builtin())
        out.update({k: str(values.get(k, "")).strip() for k in declared})
        for name, i in declared.items():                 # 預設值可以用內建的 {today}／{now} 與使用者給的其他資訊（例：`id: {robot}`）
            if not out[name] and i["default"] is not None:
                out[name] = subst(i["default"], out)
        return out, None

    # ---------------------------------------------------------------- 確認關卡
    def _wf_segment(self, wf, start, values):
        """從第 start 步開始、到下一個【確認】之前會改變狀態的步驟（確認關卡要列給使用者看的）；選填的沒給、會略過的不算。"""
        changing = []
        for s in wf["steps"][start - 1:]:
            if s["kind"] == "確認":
                break
            if self._wf_step_changes(s) and not ws.skipped_by(wf, s, values):
                changing.append(s)
        return changing

    @staticmethod
    def _wf_changes_text(changing, values):
        return "；".join(f"第 {s['n']} 步 {ws.show(s['title'], values)}（{s['script'][:-7]} {ws.show(s.get('args', ''), values)}）".replace(" ）", "）")
                        for s in changing)

    def workflow_guard_reason(self, remainder):
        """workflow_run 的確認說明（guard.py）。不用確認時回 None：只查詢的工作流、取消、列出、參數錯（交給 workflow_run 回錯誤）。"""
        action, target, values, err = self._wf_parse_args(remainder)
        if err or action in ("list", "cancel"):
            return None
        if action == "continue":
            job = self._wf_find_job(target)
            if not job or job.get("status") != "paused":
                return None
            wf, inputs = job["spec"], job.get("inputs") or {}
            step = wf["steps"][job["cursor"] - 2] if job["cursor"] >= 2 else None
            changing = self._wf_segment(wf, job["cursor"], inputs)
            return (f"繼續工作流「{wf['title']}」（{wf['name']}）：第 {step['n'] if step else '?'} 步【確認】{ws.show(step['text'], inputs) if step else ''}"
                    + (f"\n接下來會改變狀態的步驟：{self._wf_changes_text(changing, inputs)}" if changing else "\n接下來的步驟都只查詢")
                    + "\n" + ws.outline(wf, values=inputs))
        wf = self.load_workflow(target)
        if not wf:
            return None
        inputs, err = self._wf_check_inputs(wf, values)
        if err:
            return None
        changing = self._wf_segment(wf, 1, inputs)
        confirm = next((s for s in wf["steps"] if s["kind"] == "確認"), None)
        if not changing:
            return None
        shown = "、".join(f"{i['name']}={inputs[i['name']]}" for i in wf["inputs"] if inputs.get(i["name"]))   # 使用者給的＋預設
        return (f"執行工作流「{wf['title']}」（{wf['name']}）" + (f"，參數：{shown}" if shown else "")
                + f"\n會改變狀態的步驟：{self._wf_changes_text(changing, inputs)}"
                + "（{名稱} 是執行到那一步時依前面的輸出決定的值）" * any(ws.fill_names(wf, s) for s in changing)
                + (f"\n（第 {confirm['n']} 步【確認】會停下來再問一次）" if confirm else "") + "\n" + ws.outline(wf, values=inputs))

    # ---------------------------------------------------------------- 執行
    def workflow_run(self, remainder):
        """workflow_run 偽技能（dispatch 在確認關卡之後呼叫）：回傳給主對話的報告。這次執行（或接著做、取消）的工作編號記在
        last_workflow_job（/workflow 不用互動的入口照它讀結束的狀態；參數錯、沒有執行時是 None）。"""
        self.last_workflow_job = None
        action, target, values, err = self._wf_parse_args(remainder)
        if err:
            return err
        if action == "list":
            return self._wf_list_text()
        if action in ("continue", "cancel"):
            job = self._wf_find_job(target)
            if not job or job.get("status") != "paused":
                return ("[ERROR] 沒有停在【確認】、等著繼續的工作流" + (f"（{target}）" if target else "")
                        + "。下一步：用 workflow_run <名稱> key=value … 開始一個；最近的工作流結果在主對話的檢索清單裡（result_recall 看得到）。")
            self.last_workflow_job = job["id"]
            if action == "cancel":
                job["status"] = "cancelled"
                self._wf_store_job(job)
                return f"[PASS] 工作流 {job['spec']['name']}（{job['id']}）取消了：停在第 {job['cursor'] - 1} 步之後，後面的步驟沒有做。"
            return WorkflowRun(self, job).run()
        wf = self.load_workflow(target)
        if not wf:
            names = [w["name"] for w in self.list_workflows()]
            return (f"[ERROR] 沒有工作流 {target}。現有的：{'、'.join(names) or '（沒有）'}。下一步：照 SKILLS.md〈工作流〉的名稱寫；"
                    f"沒有適合的就用技能一步一步做。")
        problems = self.validate_workflow(wf)
        if problems:
            return (f"[ERROR] 工作流 {wf['name']} 的規格有問題，沒有執行：{'；'.join(problems[:6])}。下一步：告訴使用者規格要修正"
                    f"（{os.path.relpath(wf['path'], self.base_path)}），這次改用技能一步一步做。")
        inputs, err = self._wf_check_inputs(wf, values)
        if err:
            return err
        store = self._workflow_store()
        job = {"id": store.new_id(wf["name"]), "spec": wf, "inputs": inputs, "given": values, "status": "running", "cursor": 1,
               "steps": {str(s["n"]): {"status": "pending"} for s in wf["steps"]}, "notes": [], "created": time.strftime("%Y-%m-%d %H:%M:%S"),
               "model": self.model, "seconds": 0.0, "model_calls": 0}
        self.last_workflow_job = job["id"]
        return WorkflowRun(self, job).run()

    def _wf_store_job(self, job):
        store = self._workflow_store()
        store.save(job)
        store.prune(WORKFLOW_JOBS_KEEP)

    def _wf_find_job(self, job_id=None):
        store = self._workflow_store()
        if job_id:
            return store.load(job_id)
        for jid in reversed(store.ids()):
            job = store.load(jid)
            if job and job.get("status") == "paused":
                return job
        return None

    def _wf_list_text(self):
        wfs = self.list_workflows()
        if not wfs:
            return "[PASS] 目前沒有工作流（skills_system/workflows/ 是空的）。"
        lines = [f"[PASS] 工作流 {len(wfs)} 個（workflow_run <名稱> key=value …）"]
        for wf in wfs:
            need = "、".join(f"{i['name']}{'（選填）' if i['optional'] else ''}" for i in wf["inputs"]) or "不需要"
            lines.append(f"- {wf['name']}：{wf['description']}｜需要：{need}")
        return "\n".join(lines)


class WorkflowRun:
    """一次執行（或停在【確認】之後接著執行）：從 job["cursor"] 開始，一步一步做到結束、失敗或下一個【確認】。"""

    def __init__(self, agent, job):
        self.a, self.job, self.wf = agent, job, job["spec"]
        self.store = agent._workflow_store()
        self.outputs = {}          # 步驟 → 輸出原文（這次執行過的；停下來再繼續時從存檔讀回）

    # ------------------------------------------------ 共用
    def title(self, s):
        """給人看的步驟標題：需要的資訊代進去（規格裡的「只改 {robot} 那一段」→「只改 tb1 那一段」）。"""
        return ws.show(s["title"], self.job["inputs"])

    def note(self, text):
        print(text)
        try:
            self.store.append(self.job["id"], "events.jsonl", {"text": text})
        except OSError:
            pass
        cb = getattr(self.a, "progress_callback", None)
        if cb:
            try:
                cb(text)
            except Exception:   # noqa: BLE001
                pass

    def state(self, n):
        return self.job["steps"][str(n)]

    def output(self, n):
        if n in self.outputs:
            return self.outputs[n]
        st = self.state(n)
        text = self.a.result_text(st.get("file") or st.get("rid"))   # 停在【確認】之後接著做：記憶體裡沒有了，讀回存檔的原文
        if text is not None:
            self.outputs[n] = text
        return self.outputs.get(n, st.get("head", ""))

    def context(self, upto):
        """判斷點看得到的：需要的資訊、前面每一個做過的【執行】步的輸出（每份最多 WORKFLOW_CONTEXT_CHARS 字，完整的在存檔）。"""
        parts = [_w("context_inputs", inputs="、".join(f"{k}={v}" for k, v in self.job["inputs"].items() if k not in ws.BUILTIN)
                    or _w("context_no_inputs"))]
        for s in self.wf["steps"]:
            if s["n"] >= upto or s["kind"] != "執行":
                continue
            st = self.state(s["n"])
            if st["status"] != "done" and not st.get("rid"):
                continue
            parts.append(_w("context_output", n=s["n"], title=self.title(s), command=st.get("command", ""), rid=st.get("rid", "?"),
                            output=_clip(self.output(s["n"]), WORKFLOW_CONTEXT_CHARS)))
        return "\n\n".join(parts)

    def ask(self, kind, system, user, schema):
        """判斷點的一次模型呼叫（記進 calls.jsonl）。回傳 dict 或 None。"""
        self.job["model_calls"] += 1
        raw, data, err = "", None, None
        try:
            res = self.a._timed_chat(f"workflow_{kind}", model=self.a.model,
                                     messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                     format=schema, options={"temperature": 0.1, "num_ctx": NUM_CTX, "num_predict": 2048}, think=False)
            raw = res["message"]["content"]
            data = json.loads(raw)
        except Exception as e:   # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        try:
            self.store.append(self.job["id"], "calls.jsonl", {"kind": kind, "system": system, "user": user, "response": raw, "error": err})
        except OSError:
            pass
        return data if isinstance(data, dict) else None

    # ------------------------------------------------ 一步一步
    def run(self):
        t0 = time.time()
        self.job["status"] = "running"
        steps = self.wf["steps"]
        resumed = self.job["cursor"] > 1
        if resumed:
            prev = steps[self.job["cursor"] - 2]
            if prev["kind"] == "確認" and self.state(prev["n"])["status"] == "paused":
                self.state(prev["n"]).update(status="done", why="使用者在確認關卡核准（workflow_run --continue）")
        self.note(f"🧩 工作流 {self.wf['name']}（{self.wf['title']}）{'從第 ' + str(self.job['cursor']) + ' 步接著做' if resumed else '開始'}"
                  f"：共 {len(steps)} 步")
        end = None
        while self.job["cursor"] <= len(steps):
            s = steps[self.job["cursor"] - 1]
            st = self.state(s["n"])
            if s["kind"] == "執行":
                ok = self.do_exec(s, st)
                self.save()
                if not ok:
                    end = "failed"
                    break
                self.job["cursor"] += 1
            elif s["kind"] == "檢查":
                to = self.do_check(s, st)
                self.save()
                if to == "end":
                    end = "ended"
                    break
                self.job["cursor"] = to if isinstance(to, int) else self.job["cursor"] + 1
                for k in range(s["n"] + 1, self.job["cursor"]):
                    self.state(k).update(status="skipped", why=f"第 {s['n']} 步的判斷跳過")
            elif s["kind"] == "確認":
                st.update(status="paused")
                self.job["cursor"] += 1                # 繼續時從下一步開始（這一步在 --continue 的確認關卡上核准）
                self.job["status"] = "paused"
                self.job["seconds"] += round(time.time() - t0, 1)
                self.save()
                self.note(f"⏸️ 工作流停在第 {s['n']} 步【確認】：{ws.show(s['text'], self.job['inputs'])}")
                return self.report()
            else:   # 告知
                st.update(status="done", said=s["text"])
                self.job["cursor"] += 1
        if end is None:
            end = self.do_success()
        self.job["status"] = end
        self.job["seconds"] += round(time.time() - t0, 1)
        self.save()
        self.note(f"🧩 工作流 {self.wf['name']}：{_STATUS_TEXT[end]}（{self.job['seconds']:.0f} 秒）")
        return self.report()

    def save(self):
        self.a._wf_store_job(self.job)

    def do_exec(self, s, st):
        values = dict(self.job["inputs"])
        for x in self.wf["steps"][: s["n"] - 1]:      # 前面的判斷點決定過的值沿用：同一個名稱同一個值，不再問一次、前後一致
            values.update(self.state(x["n"]).get("values") or {})
        empty_optional = ws.skipped_by(self.wf, s, values)
        if empty_optional:
            st.update(status="skipped", why=f"選填的 {'、'.join(empty_optional)} 沒有給")
            self.note(f"⏭️ 第 {s['n']} 步 {self.title(s)}：{st['why']}，略過")
            return True
        fill = [p for p in ws.fill_names(self.wf, s) if p not in values]
        error_text = None
        for attempt in (1, 2):
            if fill:
                got = self.fill_values(s, fill, error_text)
                if got is None:
                    st.update(status="failed", why="判斷點的模型沒有給出可以用的值（見 calls.jsonl）")
                    return False
                missing = [k for k in fill if not str(got.get(k, "")).strip()]
                if missing:
                    st.update(status="failed", values=got, why=f"前面的輸出找不到 {'、'.join(missing)} 的值：{got.get('_reason', '')}")
                    return False
                values.update({k: got[k] for k in fill})
                st["values"] = {k: got[k] for k in fill}
                st["fill_reason"] = got.get("_reason", "")
            args = fill_template(s.get("args", ""), values, s["script"])
            command = f"scripts/{s['script']} {args}".strip()
            st["command"] = command[:600]
            self.note(f"🧩 第 {s['n']}/{len(self.wf['steps'])} 步【執行】{self.title(s)}：{s['script'][:-7]} {_clip(args, 160)}")
            before = len(self.a.trajectory)
            out = self.a._run_tool_once({"action": {"command": f"scripts/{s['script']}", "args": args}}, approved=True) or ""
            rec = next((r for r in reversed(self.a.trajectory[before:]) if r.get("kind") == "exec"), None)
            self.outputs[s["n"]] = out
            st.update(rid=rec.get("id") if rec else None, file=self.a.result_file_path(rec["id"]) if rec else None,
                      head=(out.strip().splitlines() or [""])[0][:300])
            failed_skill = out.lstrip().startswith(("[ERROR]", "[DENIED]"))
            check_ok = (not s.get("check")) or _has(out, [subst(w, values) for w in s["check"]])
            if not failed_skill and check_ok:
                st["status"] = "done"
                return True
            why = (f"技能回報錯誤：{st['head']}" if failed_skill else
                   f"檢查沒過：輸出沒有「{'」或「'.join(s['check'])}」（{st['head']}）")
            if failed_skill and fill and attempt == 1 and not out.lstrip().startswith("[DENIED]"):
                error_text = _clip(out, 1500)        # 值是模型填的：帶著錯誤請它改一次（[ERROR] 的技能沒有改變任何狀態）
                self.note(f"↩️ 第 {s['n']} 步：{why[:160]}，請判斷點改一次值")
                continue
            st.update(status="failed", why=why)
            return False
        return False

    def fill_values(self, s, names, error_text=None):
        props = {k: {"type": "string"} for k in names}
        schema = {"type": "object", "properties": {"values": {"type": "object", "properties": props, "required": names},
                                                   "reason": {"type": "string"}}, "required": ["values", "reason"]}
        user = _w("fill_user", title=self.wf["title"], name=self.wf["name"], purpose=self.wf["purpose"][:400],
                  outline=ws.outline(self.wf, s["n"], self.job["inputs"]), n=s["n"], step=ws.show(s["text"], self.job["inputs"]),
                  script=s["script"], args=ws.show(s.get("args", ""), self.job["inputs"]), names="、".join(names),
                  context=self.context(s["n"]))
        if error_text:
            user += "\n\n" + _w("fill_retry", error=error_text)
        data = self.ask("fill", _read_prompt("fill.md"), user, schema)
        if not data or not isinstance(data.get("values"), dict):
            return None
        out = {k: str(data["values"].get(k, "")).strip() for k in names}
        out["_reason"] = str(data.get("reason") or "").strip()[:300]
        return out

    def do_check(self, s, st):
        src = s.get("source") or next((x["n"] for x in reversed(self.wf["steps"][: s["n"] - 1])
                                       if x["kind"] == "執行" and self.state(x["n"])["status"] == "done"), None)
        out = self.output(src) if src and self.state(src)["status"] == "done" else ""
        branches = s.get("branches") or []
        for i, b in enumerate(branches):
            if b["when"] and _has(out, b["when"]):
                return self._take(s, st, i, f"第 {src} 步的輸出有「{'」或「'.join(b['when'])}」", "程式")
        other = next((i for i, b in enumerate(branches) if b["when"] is None), None)
        if other is not None:
            return self._take(s, st, other, "前面的條件都不成立", "程式")
        options = ([_w("check_option_branch", when="」或「".join(b["when"]),
                       target=_w("check_target_end") if b["to"] == "end" else _w("check_target_step", to=b["to"])) for b in branches]
                   if branches else [_w("check_option_continue"), _w("check_option_stop")])
        schema = {"type": "object", "properties": {"choice": {"type": "integer", "minimum": 0, "maximum": len(options) - 1},
                                                   "reason": {"type": "string"}}, "required": ["choice", "reason"]}
        user = _w("check_user", title=self.wf["title"], outline=ws.outline(self.wf, s["n"], self.job["inputs"]), n=s["n"],
                  step=ws.show(s["text"], self.job["inputs"]), options="\n".join(f"{i}. {o}" for i, o in enumerate(options)),
                  context=self.context(s["n"]))
        data = self.ask("check", _read_prompt("check.md"), user, schema)
        choice = data.get("choice") if data else None
        if not isinstance(choice, int) or not 0 <= choice < len(options):
            st.update(status="done", branch="結束", decided_by="程式", why="判斷點沒有給出可以用的選擇，保守結束")
            return "end"
        reason = str(data.get("reason") or "")[:300]
        if not branches:
            st.update(status="done", branch=options[choice], decided_by="模型", why=reason)
            return "end" if choice == 1 else None
        return self._take(s, st, choice, reason, "模型")

    def _take(self, s, st, i, why, who):
        b = s["branches"][i]
        label = ("其他" if b["when"] is None else f"「{'」或「'.join(b['when'])}」") + " → " + ("結束" if b["to"] == "end" else f"第 {b['to']} 步")
        st.update(status="done", branch=label, decided_by=who, why=why)
        self.note(f"🧩 第 {s['n']} 步【檢查】{label}（{who}判斷：{why[:120]}）")
        return b["to"]

    def do_success(self):
        """成功判準（程式跑）：都過＝done；有沒過的＝unverified。會改變狀態的檢查命令不執行（標成沒有驗證）。"""
        crit = self.wf.get("success") or []
        results, bad = [], False
        for c in crit:
            if c.get("manual"):
                results.append({"text": c["text"], "ok": None, "why": "照文字，程式沒有驗證"})
                continue
            words = [subst(w, self.job["inputs"]) for w in c["expect"]]
            if c.get("step"):
                st = self.state(c["step"])
                if st["status"] != "done":
                    results.append({"text": c["text"], "ok": None, "why": f"第 {c['step']} 步沒有做（{st['status']}）"})
                    continue
                ok = _has(self.output(c["step"]), words)
                results.append({"text": c["text"], "ok": ok, "why": f"第 {c['step']} 步的輸出{'有' if ok else '沒有'}「{'」或「'.join(words)}」"})
                bad |= not ok
                continue
            args = fill_template(c.get("args", ""), self.job["inputs"], c["script"])
            parsed = {"action": {"command": f"scripts/{c['script']}", "args": args}}
            if self.a.state_change_info(parsed):
                results.append({"text": c["text"], "ok": None, "why": "檢查用的命令會改變狀態，沒有執行"})
                continue
            out = self.a._run_tool_once(parsed, approved=False) or ""
            head = (out.strip().splitlines() or [""])[0][:200]
            ok = not out.lstrip().startswith("[ERROR]") and _has(out, words)
            results.append({"text": c["text"], "ok": ok, "why": f"{c['script'][:-7]} {args} → {'有' if ok else '沒有'}「{'」或「'.join(words)}」（{head}）"})
            bad |= not ok
        self.job["success"] = results
        return "unverified" if bad else "done"

    # ------------------------------------------------ 報告
    def report(self):
        job, wf = self.job, self.wf
        status = job["status"]
        n_done = sum(1 for s in wf["steps"] if self.state(s["n"])["status"] == "done")
        took = f"{job['seconds']:.0f} 秒"
        if status == "done":
            head = f"[PASS] 工作流 {wf['name']}（{wf['title']}）完成：{n_done}/{len(wf['steps'])} 步做了，成功判準都過（{took}）"
        elif status == "unverified":
            head = f"[PASS] 工作流 {wf['name']} 的步驟都做了，但成功判準沒過（{took}）：回答時照實說明，請使用者確認"
        elif status == "ended":
            last = next((self.state(s["n"]) for s in reversed(wf["steps"]) if s["kind"] == "檢查" and self.state(s["n"]).get("branch")), {})
            head = f"[PASS] 工作流 {wf['name']} 依判斷提早結束：{last.get('branch', '')}（{took}）——後面的步驟沒有做，照下面的結果回報"
        elif status == "paused":
            s = wf["steps"][job["cursor"] - 2]
            head = (f"[PASS] ⏸️ 工作流 {wf['name']} 停在第 {s['n']} 步【確認】：{ws.show(s['text'], job['inputs'])}（工作 {job['id']}）。下一步：直接執行 "
                    f"workflow_run --continue（系統會請使用者確認，不用先問）；使用者不要繼續就 workflow_run --cancel")
        else:
            bad = next((s for s in wf["steps"] if self.state(s["n"])["status"] == "failed"), None)
            why = self.state(bad["n"]).get("why", "") if bad else ""
            head = (f"[ERROR] 工作流 {wf['name']} 在第 {bad['n'] if bad else '?'} 步沒有完成（{why}）；後面的步驟沒有做（{took}）。"
                    f"下一步：照這一步的輸出回報原因；要修正就照輸出的下一步做，不要整個工作流重跑")
        lines = [head, "## 步驟"]
        for s in wf["steps"]:
            st = self.state(s["n"])
            mark = _MARK.get(st["status"], "⬜")
            line = f"{s['n']}. {mark}【{s['kind']}】" + ws.show(s["text"] if s["kind"] == "告知" else s["title"], self.job["inputs"])
            if s["kind"] == "執行" and st.get("rid"):
                vals = st.get("values")
                flat = lambda v: _clip(" ⏎ ".join(str(v).splitlines()), 80)   # noqa: E731  多行的值（紀錄的內容）在報告裡排成一行
                line += (f"（{'、'.join(f'{k}={flat(v)}' for k, v in vals.items())}，模型依前面的輸出決定）" if vals else "")
                line += f" → #{st['rid']}：{st.get('head', '')}"
            elif s["kind"] == "檢查" and st.get("branch"):
                line += f"：{st['branch']}（{st.get('decided_by', '')}判斷：{_clip(st.get('why', ''), 120)}）"
            if st["status"] in ("skipped", "failed") and st.get("why"):
                line += f"（{st['why']}）"
            lines.append(line)
        if job.get("success"):
            lines.append("## 成功判準（程式檢查）")
            for r in job["success"]:
                lines.append(f"- {'✅' if r['ok'] else '❌' if r['ok'] is False else '—'} {r['why']}")
        if wf.get("pitfalls") and status in ("failed", "ended", "unverified"):
            lines.append("## 規格的注意事項\n" + "\n".join(f"- {p}" for p in wf["pitfalls"][:4]))
        lines.append(f"（工作 {job['id']}，紀錄在 logs/{WORKFLOW_JOBS_DIRNAME}/{job['id']}/；依上面的結果回答使用者，引用具體的值與名稱；"
                     f"要看某一步的完整輸出用 result_recall <#編號> \"<問題>\"）")
        return "\n".join(lines)
