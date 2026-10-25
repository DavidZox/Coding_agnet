"""PlanMixin：/plan 模式——任務引擎的計畫審核。計畫由任務引擎規劃（agent_core/task_engine.py），使用者看、改、核准後由任務引擎照計畫做。

流程：
1. 草稿：/plan on 之後的新任務交給任務引擎規劃（task_plan，mode＝plan），草稿不進主對話，存在 self.plan（任務引擎的 job，status＝draft；
   logs/task_jobs/<編號>/ 也有一份）；也可以用 /plan add 從空的草稿一條條加。
2. 修改：使用者直接下指令（/plan add／insert／edit／del／move，完全不經過模型），或用自然語言說要怎麼改——這時規劃 session 只輸出
   「要套用的操作」（format=PLAN_OPS_SCHEMA），由 harness 套在草稿上。小模型每次重寫整份時會把 4 步變 2 步、改掉沒提到的步驟，所以不讓它
   重寫。每一步照任務引擎同一套規則整理（技能存在、會不會改變狀態），有問題列在草稿下面。
3. 核准（y）：整份計畫標明的狀態變更都核准了。使用者的任務放進主對話，harness 不經過模型直接執行 task_run --continue <工作>
   （take_task_continuation；計畫都核准過了，不會再問一次），任務引擎照計畫做（不重排：使用者核准的就是這一份），報告照一般工具結果
   進主對話，主對話依報告回答。"""
import re
import time

from . import prompt_files
from .config import TASK_MAX_ITEMS
from .schemas import PLAN_OPS_SCHEMA

_PLAN_EDIT = "orchestra/plan_edit.md"   # 用說的改草稿的 prompt

PLAN_HELP = ("y＝核准並執行｜n＝取消｜/plan add <技能>：<要做什麼>｜/plan insert <N> <技能>：<要做什麼>｜"
             "/plan edit <N> <技能>：<要做什麼>｜/plan del <N>｜/plan move <N> <M>｜/plan show｜其他文字＝用說的改（AI 只提出要改哪幾條）")
_OWN_PLAN = "（使用者自己列的計畫）"


class PlanMixin:

    # ---------------------------------------------------------------- 狀態與顯示
    def plan_status(self):
        """None（沒有草稿）／draft（草稿，等使用者核准）。"""
        return "draft" if self.plan and self.plan.get("status") == "draft" else None

    def plan_text(self):
        if not self.plan or not self.plan["items"]:
            return "（草稿是空的：用 /plan add <技能>：<要做什麼> 加一步）"
        return "\n".join(self.task_item_text(it) for it in self.plan["items"])

    def plan_view(self):
        """給使用者看的草稿（CLI 印出、Web 的計畫卡片）。"""
        warn = ""
        if self.plan and (self.plan.get("issues") or self.plan_error):
            warn = "\n⚠️ " + "；".join(([self.plan_error] if self.plan_error else []) + list(self.plan.get("issues") or []))
        return f"{self.plan_text()}{warn}\n\n{PLAN_HELP}"

    def plan_stats(self):
        """Web 狀態列用。"""
        if not self.plan:
            return None
        return {"status": self.plan_status(), "total": len(self.plan["items"]), "text": self.plan_text()}

    def _plan_save(self):
        if self.plan:
            self._task_save(self.plan)

    # ---------------------------------------------------------------- 草稿
    def _plan_new(self, task):
        store = self._task_store()
        return {"id": store.new_id("plan"), "profile": "ops", "task": task, "mode": "plan", "status": "draft", "items": [], "plans": [],
                "replans": 0, "plan_calls": 0, "model_calls": 0, "seconds": 0.0, "issues": [],
                "created": time.strftime("%Y-%m-%d %H:%M:%S"), "model": self.model}

    def plan_start_draft(self, task):
        """/plan on 之後的新任務：任務引擎規劃第一版草稿。回傳給使用者看的文字。"""
        self.plan_error = None
        job, err = self.task_plan(task, mode="plan")
        if job is None:
            self.plan = self._plan_new(task)
            self.plan_error = (err or "規劃不出步驟").replace("[ERROR] ", "") + "；請用 /plan add 自己加"
            self._plan_save()
        else:
            self.plan = job
        return self.plan_view()

    def _plan_renumber(self):
        issues = []
        for i, it in enumerate(self.plan["items"], 1):
            it["n"] = i
        for it in self.plan["items"]:
            _, problems = self._task_item(dict(it, check=it.get("check")), it["n"])
            issues += problems
        self.plan["issues"] = issues

    def _plan_make_item(self, skill, goal, n):
        raw = {"title": goal[:30], "goal": goal, "skills": [skill] if skill else [], "workflow": "", "workflow_args": "",
               "changes_state": False, "check": None}
        if skill and self.load_workflow(skill):        # 「/plan add stuck_package_fix：wp_id=WP_1」→ 工作流的步驟
            raw.update(skills=[], workflow=skill, workflow_args=goal if "=" in goal else "")
        it, _ = self._task_item(raw, n)
        return it

    def _parse_step_text(self, text):
        """「技能：要做什麼」／「技能 要做什麼」→ (技能或工作流, 要做什麼)；開頭不是技能或工作流的名稱就當成不指定技能的一步。"""
        text = " ".join(str(text or "").split())
        names = sorted(set(self.task_skill_names()) | {w["name"] for w in self.list_workflows()}, key=len, reverse=True)
        for name in names:
            if text == name or text.startswith((name + "：", name + ":", name + " ")):
                return name, text[len(name):].lstrip("：: ").strip() or name
        return "", text

    # ---------------------------------------------------------------- 修改（使用者指令與規劃 session 共用）
    def _plan_apply(self, op):
        items = self.plan["items"]
        kind = str(op.get("op") or "")
        n, to = int(op.get("step") or 0), int(op.get("to") or 0)
        goal = " ".join(str(op.get("goal") or "").split())[:600]
        skill = str(op.get("skill") or "").strip()
        new = self._plan_make_item(skill, goal or skill, n or len(items) + 1) if (goal or skill) else None
        label = lambda it: f"{'工作流 ' + it['workflow'] if it['workflow'] else ('、'.join(it['skills']) or '（不指定技能）')}：{it['goal']}"   # noqa: E731
        if kind in ("add", "insert") and new is None:
            return f"{kind}：沒有內容，略過"
        if kind == "add":
            if len(items) >= TASK_MAX_ITEMS:
                return f"已經 {TASK_MAX_ITEMS} 步，沒有再加"
            items.append(new)
            return f"加在第 {len(items)} 步：{label(new)}"
        if not 1 <= n <= len(items) + (1 if kind == "insert" else 0):
            return f"{kind}：沒有第 {n} 步，略過"
        if kind == "insert":
            if len(items) >= TASK_MAX_ITEMS:
                return f"已經 {TASK_MAX_ITEMS} 步，沒有再加"
            items.insert(n - 1, new)
            return f"插在第 {n} 步：{label(new)}"
        if kind == "edit":
            old = items[n - 1]
            if new is not None:                       # skill 空字串＝這一步不指定技能；goal 空的就留原本的
                if not goal:
                    new = self._plan_make_item(skill, old["goal"], n)
                items[n - 1] = new
            return f"改第 {n} 步：{label(items[n - 1])}"
        if kind == "delete":
            gone = items.pop(n - 1)
            return f"刪掉第 {n} 步：{label(gone)}"
        if kind == "move":
            if not 1 <= to <= len(items):
                return f"move：沒有第 {to} 步，略過"
            items.insert(to - 1, items.pop(n - 1))
            return f"第 {n} 步移到第 {to} 步"
        return f"不認得的操作「{kind}」，略過"

    def plan_edit_command(self, text):
        """/plan add|insert|edit|del|move|show …（使用者直接改，不經過模型）。沒有草稿時 add 會開一份新的空草稿。
        回傳 (是否處理了, 給使用者看的文字)。"""
        m = re.match(r"^/plan\s+(add|insert|edit|del|delete|move|show)\b\s*(.*)$", text.strip(), re.I | re.S)
        if not m:
            return False, ""
        verb, rest = m.group(1).lower(), m.group(2).strip()
        if verb == "show":
            return True, (self.plan_view() if self.plan else "目前沒有計畫草稿。")
        if self.plan is None:
            if verb != "add":
                return True, "目前沒有草稿：先 /plan on 再送出任務讓 AI 規劃，或用 /plan add <技能>：<要做什麼> 自己開始。"
            self.plan = self._plan_new(_OWN_PLAN)
        nums = re.findall(r"\d+", rest)
        if verb == "add":
            skill, goal = self._parse_step_text(rest)
            note = self._plan_apply({"op": "add", "skill": skill, "goal": goal})
        elif verb in ("insert", "edit"):
            num = re.match(r"^(\d+)\s+(.*)$", rest, re.S)
            if not num:
                return True, f"用法：/plan {verb} <N> <技能>：<要做什麼>"
            skill, goal = self._parse_step_text(num.group(2))
            note = self._plan_apply({"op": verb, "step": int(num.group(1)), "skill": skill, "goal": goal})
        elif verb in ("del", "delete"):
            if not nums:
                return True, "用法：/plan del <N>"
            note = self._plan_apply({"op": "delete", "step": int(nums[0])})
        else:
            if len(nums) < 2:
                return True, "用法：/plan move <N> <M>"
            note = self._plan_apply({"op": "move", "step": int(nums[0]), "to": int(nums[1])})
        self.plan_error = None
        self._plan_renumber()
        self._plan_save()
        return True, f"・{note}\n\n{self.plan_view()}"

    def _plan_revise(self, feedback):
        """自然語言的修改意見：規劃 session 只輸出操作（add／insert／edit／delete／move），harness 套用。"""
        system = prompt_files.load(_PLAN_EDIT, "system")   # 文字在 prompts/orchestra/plan_edit.md
        user = prompt_files.load(_PLAN_EDIT, "user", skills=self._task_catalog(), workflows=self._task_workflow_catalog(),
                                 draft=self.plan_text(), feedback=feedback)
        _, data = self._task_call(self.plan, "plan_edit", [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                  PLAN_OPS_SCHEMA, num_predict=2048)
        ops = [o for o in (data or {}).get("ops") or [] if isinstance(o, dict)]
        if not ops:
            return "edited", f"沒看懂要改哪一條，草稿沒有變動（可以用 /plan edit／del／insert 直接改）。\n\n{self.plan_view()}"
        # 模型給的編號都是對照「原本的草稿」寫的；依序套用時前面的插入／刪除會讓後面的編號位移（實測：先插入一步再
        # 「刪第 5 步」，刪到的是原本的第 4 步）。所以先把編號換成原本那一步的物件，套用時再查它現在在第幾步。
        original = list(self.plan["items"])
        refs = []
        for o in ops:
            n, to = int(o.get("step") or 0), int(o.get("to") or 0)
            refs.append((o, original[n - 1] if 1 <= n <= len(original) else None,
                         original[to - 1] if 1 <= to <= len(original) else None, n, to))
        notes = []
        for o, ref, to_ref, n, to in refs:
            o = dict(o)
            items = self.plan["items"]
            if o.get("op") in ("edit", "delete", "move", "insert"):
                if ref is not None and any(x is ref for x in items):
                    o["step"] = next(i for i, x in enumerate(items) if x is ref) + 1
                elif o.get("op") == "insert" and n == len(original) + 1:
                    o["step"] = len(items) + 1          # 插在原本最後一步之後＝加在最後
                else:
                    notes.append(f"{o.get('op')}：原本的第 {n} 步已經不在，略過")
                    continue
            if o.get("op") == "move":
                if to_ref is None or not any(x is to_ref for x in items):
                    notes.append(f"move：原本的第 {to} 步已經不在，略過")
                    continue
                o["to"] = next(i for i, x in enumerate(items) if x is to_ref) + 1
            notes.append(self._plan_apply(o))
        self._plan_renumber()
        self._plan_save()
        return "edited", "\n".join(f"・{n}" for n in notes) + f"\n\n{self.plan_view()}"

    # ---------------------------------------------------------------- 核准
    def plan_handle_input(self, text):
        """草稿等待核准時使用者的輸入（CLI 與 Web 共用）：y 核准／n 取消／/plan 指令／其他文字＝自然語言修改。
        回傳 (結果, 給使用者看的文字)，結果是 approved／rejected／edited。"""
        choice = text.strip()
        if choice.lower() == "y":
            if not self.plan["items"]:
                return "edited", "草稿是空的，不能核准：先用 /plan add 加步驟。"
            broken = [str(it["n"]) for it in self.plan["items"] if it.get("broken")]
            if broken:
                return "edited", (f"第 {'、'.join(broken)} 步做不了（見草稿下面的 ⚠️），先用 /plan edit 改好、或 /plan del 刪掉再核准。\n\n"
                                  + self.plan_view())
            plan_text = self.plan_text()
            self.plan_approve()
            return "approved", f"✅ 計畫已核准，交給任務引擎照計畫做：\n{plan_text}"
        if choice == "" or choice.lower() in ("n", "no", "/plan done", "/plan off"):
            self.plan_clear()
            return "rejected", "🚫 已取消計畫，本次任務不會執行。"
        handled, msg = self.plan_edit_command(choice)
        if handled:
            return "edited", msg
        return self._plan_revise(choice)

    def plan_approve(self):
        """核准：整份計畫標明的狀態變更都核准了；使用者的任務進主對話，harness 下一步直接執行 task_run --continue（不經過模型、不再確認）。"""
        job = self.plan
        for it in job["items"]:
            it["approved"] = bool(it["changes_state"])
        job["status"] = "approved"
        job["approved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        job["approved_items"] = [it["title"] for it in job["items"]]   # 使用者核准的那一版（改過的草稿）
        self._task_save(job)
        self.task_job = job
        self.task_pending_approval = job["id"]
        task = job["task"] if job["task"] != _OWN_PLAN else f"照我列的計畫做：\n{self.plan_text()}"
        self.messages.append({"role": "user", "content": task})
        self.add_trajectory_boundary("plan_confirmed", plan=self.plan_text())
        self.plan = None

    def plan_clear(self):
        if self.plan and self.plan.get("status") == "draft":
            self.plan["status"] = "cancelled"
            self._plan_save()
        self.plan = None
        self.plan_error = None
