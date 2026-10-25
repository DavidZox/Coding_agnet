"""任務引擎（agent_core/task_engine.py）與 Plan 模式（agent_core/plan.py）的離線自我測試：假的 ollama.chat 照劇本回答，
不需要 Ollama、不需要 docker（容器的狀態用假的）；worker 用的是真的本機檔案技能（view_file、file_ops、list_dir）。

    python3 evals/task/selftest.py

測的是 harness 的程式把關（不是模型能力；模型能力用 evals/ops/run.py 量）：
- 規劃：技能不存在、腳本路徑換成技能名稱、會改變狀態的標記、查詢的步驟不用檢查 → 有問題交回修一次；第一步就要改變狀態時，
  確認關卡的說明是整份計畫，核准才執行；同一個任務不重新規劃；報告、存檔（job.json、calls.jsonl、events.jsonl、report.md）、不再提煉；
- 先查再確認：開頭只查詢的步驟直接做 → 照查到的事實重排 → 停下來（⏸️）→ harness 用 take_task_continuation 接著問 → 核准才改；
  取消；新的使用者訊息之後不再自動接著問、任務還留著；
- worker：沒核准的狀態變更 [DENIED]、沒用技能就說做完推回去一次、這一步不能用的技能、檢查沒過換一個 worker 重試、再沒過標成「檢查沒過」繼續；
- 事實的核對：每條附出處（#編號：這一步或前面各步的工具結果，前面的讀回存檔），名稱與數值要在那份輸出裡；對不上的交回改一次，還是不行就拿掉；
- worker 說「沒有完成」：對照這一步的目標問一次做到了沒有（查到的結果有問題也算做到），做到了不重試；
- 檢查出錯（[ERROR]）：對照目標問一次做到了沒有（只看系統記下的動作與檢查的輸出）——沒做到跟檢查沒過一樣重試，做到了算完成、標明沒有驗證；
- 失敗：自動模式重排剩下的步驟（那一步標成「重排了」）；Plan 模式不重排、停下來；
- 程式看得出的前提：在停著的容器裡做事排在啟動它之前、使用者提到手冊卻沒有先讀；規劃看得到每個容器的狀態；
- 做不了的計畫（要改變狀態卻沒有技能、列的技能都不存在、工作流的參數不對）修一次還是這樣就不執行；要寫檔卻沒列 file_ops 交回修；
- 工作流的步驟：交給工作流的執行器（它的每一步當事實）；有【確認】、不存在、參數不對的不能放進計畫；整件事就是一個工作流時交回主對話；
  工作流的名稱寫在 skills、參數用逗號隔開的照整理；目標寫了工作流卻沒填 workflow 交回修；
- Plan 模式：任務引擎規劃草稿、/plan add／edit／move／del、用說的改（只套用操作）、核准後照計畫做（不再確認、不重排）、取消；
- 存檔只留最近幾次；/clear 清掉還沒開始、等確認的任務。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts"]

NOTE_WF = """---
type: Workflow
title: 附加一行紀錄
description: 在紀錄檔最後附加一行，再讀回來確認（測試用）
version: 0.1.0
dependencies: ["file_ops", "view_file"]
changes_state: true
---
# 用途
測試用。

# 需要的資訊
* `{file}`：紀錄檔
* `{text}`：要附加的字

# 步驟
1. 【執行】附加到 {file}：`EXECUTE: scripts/file_ops_cmd.py append {file} --text "{text}"`　檢查：輸出有「已附加」
2. 【執行】讀回來：`EXECUTE: scripts/cat_cmd.py {file}`　檢查：輸出有「{text}」

# 成功判準
* 第 2 步的輸出有「{text}」

# 異常與注意事項
* 測試用。
"""
CONFIRM_WF = NOTE_WF.replace("title: 附加一行紀錄", "title: 有確認的").replace(
    "2. 【執行】讀回來", "2. 【確認】要不要接著讀回來\n3. 【執行】讀回來").replace("第 2 步的輸出", "第 3 步的輸出")


class FakeTask:
    """規劃（第一版、修正、重排）依序回 plans；worker 依序回 steps；收尾回 wrapups；事實的修正回 fixes；「沒有完成」時對照目標的問題回 goals；
    Plan 模式的修改回 ops；
    主對話回 mains；其他 session 回固定文字。事實的 ref 寫 LAST＝這個 worker 最近一次工具結果的編號、FIRST＝這個任務第一次工具結果的編號
    （前面的步驟執行的；執行時才知道）。"""

    def __init__(self, plans=(), steps=(), wrapups=(), fixes=(), ops=(), mains=(), goals=()):
        self.plans, self.steps, self.wrapups, self.fixes, self.ops, self.mains, self.goals = (
            list(x) for x in (plans, steps, wrapups, fixes, ops, mains, goals))
        self.plan_msgs, self.worker_msgs, self.fix_msgs, self.goal_msgs = [], [], [], []

    @staticmethod
    def _last_rid(messages):
        for m in reversed(messages or []):
            hit = re.match(r"\[tool result #(\d+)\]", m.get("content") or "")
            if hit:
                return hit.group(1)
        return "?"

    def _first_rid(self):
        for msgs in self.worker_msgs:
            for m in msgs:
                hit = re.match(r"\[tool result #(\d+)\]", m.get("content") or "")
                if hit:
                    return hit.group(1)
        return "?"

    def _refs(self, data, messages):
        for f in data.get("facts") or []:
            if f.get("ref") == "LAST":
                f["ref"] = self._last_rid(messages)
            elif f.get("ref") == "FIRST":
                f["ref"] = self._first_rid()
        return data

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = sorted((format or {}).get("properties", {})) if isinstance(format, dict) else []
        if "understanding" in props and "items" in props:
            self.plan_msgs.append(list(messages or []))
            data = self.plans.pop(0) if self.plans else plan()
        elif props == ["action", "facts", "reply", "thought"]:
            self.worker_msgs.append(list(messages or []))
            data = self._refs(json.loads(json.dumps(self.steps.pop(0))) if self.steps else done("完成"), messages)
        elif props == ["done", "facts", "summary"]:
            data = self._refs(self.wrapups.pop(0) if self.wrapups else {"done": False, "summary": "沒做完", "facts": []}, messages)
        elif props == ["goal_met", "summary"]:
            self.goal_msgs.append(list(messages or []))
            data = self.goals.pop(0) if self.goals else {"goal_met": False, "summary": ""}
        elif props == ["facts", "summary"]:
            self.fix_msgs.append(list(messages or []))
            data = self._refs(self.fixes.pop(0) if self.fixes else {"facts": [], "summary": ""}, messages)
        elif props == ["ops"]:
            data = self.ops.pop(0) if self.ops else {"ops": []}
        elif "action" in props:
            data = self.mains.pop(0) if self.mains else {"thought": "", "reply": "好的。", "action": None}
        else:
            return {"message": {"content": "（摘要）"}, "prompt_eval_count": 100, "eval_count": 20}
        return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 100, "eval_count": 20}

    @property
    def plan_calls(self):
        return len(self.plan_msgs)


def step(cmd, args=""):
    return {"thought": "照做", "reply": "執行中", "action": {"command": cmd, "args": args}, "facts": []}


def done(reply, facts=()):
    return {"thought": "回報", "reply": reply, "action": None, "facts": [dict(f) for f in facts]}


def fact(text, ref="LAST"):
    return {"text": text, "ref": ref}


def item(title, goal, skills, changes=False, check=None, workflow="", wargs=""):
    return {"title": title, "goal": goal, "skills": skills, "workflow": workflow, "workflow_args": wargs, "changes_state": changes,
            "check": check}


def plan(*items, summary="測試計畫", report="修改前後的值"):
    return {"understanding": "測試", "summary": summary, "items": list(items), "report": report}


def task(text):
    return {"action": {"command": "scripts/task_run_cmd.py", "args": f'"{text}"'}}


CHECK20 = {"skill": "view_file", "args": "config/cam.yaml", "expect": r"exposure: 20"}


def scenario(name, fn, results):
    tmp = tempfile.mkdtemp(prefix="task_selftest_")
    for it in COPY:
        shutil.copytree(os.path.join(PROJECT, it), os.path.join(tmp, it), ignore=shutil.ignore_patterns("__pycache__", "drafts"))
    for wf_name, text in (("note_append", NOTE_WF), ("confirm_test", CONFIRM_WF)):
        with open(os.path.join(tmp, "skills_system", "workflows", f"{wf_name}.md"), "w", encoding="utf-8") as f:
            f.write(text)
    home = os.path.join(tmp, "work")
    os.makedirs(os.path.join(home, "config"))
    os.makedirs(os.path.join(home, "notes"))
    with open(os.path.join(home, "config", "cam.yaml"), "w", encoding="utf-8") as f:
        f.write("camera:\n  exposure: 10\n  fps: 30\n")
    os.environ["AGENT_PERF_LOG"] = "0"
    sys.path.insert(0, tmp)
    for m in [m for m in sys.modules if m.startswith(("agent_core", "skills_system"))]:
        del sys.modules[m]
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        import ollama
        from agent_core.agent import SkillAgent
        agent = SkillAgent(model="fake")
        agent.current_cwd = home
        agent._task_containers = lambda: ({}, None)      # 沒有 docker：容器的狀態用假的（需要的情境自己換）
        fn(agent, ollama, tmp, home)
        results.append((name, True, ""))
        print(f"✅ {name}")
    except Exception as e:   # noqa: BLE001
        import traceback
        results.append((name, False, traceback.format_exc()))
        print(f"❌ {name}：{e}")
    finally:
        os.chdir(cwd)
        sys.path.remove(tmp)
        shutil.rmtree(tmp, ignore_errors=True)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def job_dir(agent, job):
    return os.path.join(agent.script_dir, "logs", "task_jobs", job["id"])


# ---------------------------------------------------------------- 規劃、第一步就要改、存檔
def t_first_step_changes(agent, ollama, tmp, home):
    first = plan(item("改成 20", "把 config/cam.yaml 的 exposure 從 10 改成 20", ["scripts/file_ops_cmd.py", "no_such_skill"], True, CHECK20),
                 item("再看一次", "看 config/cam.yaml", ["view_file"], check={"skill": "view_file", "args": "x", "expect": "y"}))
    second = plan(item("改成 20", "把 config/cam.yaml 的 exposure 從 10 改成 20", ["scripts/file_ops_cmd.py"], True, CHECK20),
                  item("再看一次", "看 config/cam.yaml", ["view_file"], check={"skill": "view_file", "args": "x", "expect": "y"}))
    fake = FakeTask([first, second], [
        step("scripts/file_ops_cmd.py", "set config/cam.yaml exposure 20"),
        done("已把 exposure 從 10 改成 20", [fact("exposure 從 10 改成 20")]),
        step("scripts/cat_cmd.py", "config/cam.yaml"), done("exposure 是 20", [fact("exposure: 20")])])
    ollama.chat = fake
    act = task("把 config/cam.yaml 的 exposure 改成 20")
    guard = agent.guard_check(act)
    assert guard and guard["skill"] == "task_run" and "會改變狀態的是：第 1 步 改成 20" in guard["reason"], guard
    assert fake.plan_calls == 2 and "不在技能清單裡" in fake.plan_msgs[1][1]["content"], "技能不存在：把問題交回規劃 session 修一次"
    job = agent.task_job
    assert job["items"][0]["skills"] == ["file_ops"] and job["items"][0]["changes_state"], "腳本路徑換成技能名稱；file_ops 會改變狀態"
    assert job["items"][1]["check"] is None and not job["items"][1]["changes_state"], "查詢的步驟不用檢查"
    assert "做完檢查：view_file config/cam.yaml" in agent.guard_prompt_text(guard)
    assert agent.guard_check(act) and fake.plan_calls == 2, "同一個任務：不重新規劃"
    blocked = agent.run_tool(act, approved=False)
    assert blocked.startswith("[DENIED]") and "exposure: 10" in read(os.path.join(home, "config", "cam.yaml")), blocked
    rep = agent.run_tool(act, approved=True)
    assert rep.startswith("[PASS] 任務完成（2/2 步"), rep
    assert "exposure: 20" in read(os.path.join(home, "config", "cam.yaml"))
    assert re.search(r"exposure 從 10 改成 20（#\d+）", rep) and "檢查：view_file config/cam.yaml → 有「exposure: 20」" in rep, rep
    assert "要回報給使用者的重點：修改前後的值" in rep and fake.plan_calls == 2
    w2 = fake.worker_msgs[2]                     # 第 2 步的 worker：乾淨的 session，看得到前一步核對過的事實、規格已附上
    assert len(w2) == 2 and "第 1 步「改成 20」完成：已把 exposure 從 10 改成 20" in w2[1]["content"], w2[1]["content"][:800]
    assert re.search(r"- exposure 從 10 改成 20（#\d+）", w2[1]["content"]) and "### view_file" in w2[0]["content"]
    assert "可以用來改變狀態的技能：file_ops" in fake.worker_msgs[0][1]["content"]
    from agent_core.protocol import is_exempt_result
    assert is_exempt_result(rep, 9999), "程式寫的報告不再交給提煉"
    d = job_dir(agent, job)
    saved = json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))
    assert saved["status"] == "done" and saved["items"][0]["facts"], saved["items"][0]
    kinds = [json.loads(ln)["kind"] for ln in open(os.path.join(d, "calls.jsonl"), encoding="utf-8")]
    assert kinds[:2] == ["plan", "plan_fix"] and kinds.count("worker_start") == 2 and kinds.count("worker") == 4, kinds
    start = next(json.loads(ln) for ln in open(os.path.join(d, "calls.jsonl"), encoding="utf-8") if '"worker_start"' in ln)
    assert "## 這一步的技能規格" in start["messages"][0]["content"], "worker 的 system 與任務說明整份存檔"
    assert os.path.exists(os.path.join(d, "events.jsonl")) and read(os.path.join(d, "report.md")).startswith("[PASS] 任務完成")
    assert agent.task_last is job and job["status"] == "done"
    rec = [r for r in agent.trajectory if r.get("script") == "file_ops_cmd.py"]
    assert rec and rec[-1]["task_job"] == job["id"], "worker 的工具呼叫在軌跡上標了是哪一個任務"


# ---------------------------------------------------------------- 先查再確認
def t_survey_then_confirm(agent, ollama, tmp, home):
    cam = os.path.join(home, "config", "cam.yaml")
    first = plan(item("看現在的值", "看 config/cam.yaml 的 exposure", ["view_file"]),
                 item("改成 20", "把 exposure 改成 20", ["file_ops"], True, CHECK20))
    replanned = plan(item("改成 20", "把 config/cam.yaml 的 exposure 從 10 改成 20（第 1 步查到是 10）", ["file_ops"], True, CHECK20),
                     report="exposure 修改前後")
    fake = FakeTask([first, replanned], [
        step("scripts/cat_cmd.py", "config/cam.yaml"), done("exposure 現在是 10", [fact("exposure: 10")]),
        step("scripts/file_ops_cmd.py", "set config/cam.yaml exposure 20"), done("改好了", [fact("exposure: 10 → 20")])])
    ollama.chat = fake
    act = task("把 exposure 改成 20")
    assert agent.guard_check(act) is None and fake.plan_calls == 1, "開頭只查詢：開始時不用確認"
    out = agent.run_tool(act)
    assert out.startswith("[PASS] ⏸️ 任務") and "## 已經做完的" in out and "## 接下來的計畫" in out, out
    assert re.search(r"exposure: 10（#\d+）", out) and "第 1 步查到是 10" in out, out
    assert fake.plan_calls == 2 and "【已經做完的步驟與查到的事實】" in fake.plan_msgs[1][1]["content"]
    assert "exposure: 10" in fake.plan_msgs[1][1]["content"] and "查詢的步驟做完了" in fake.plan_msgs[1][1]["content"]
    assert "exposure: 10" in read(cam), "要改的步驟還沒確認：沒有改"
    job = agent.task_job
    assert job["status"] == "awaiting_approval" and agent.task_pending_approval == job["id"]
    cont = agent.take_task_continuation()
    assert cont and cont["action"]["args"] == f"--continue {job['id']}" and agent.task_pending_approval is None, cont
    assert json.loads(cont["raw"])["action"]["command"] == "scripts/task_run_cmd.py" and "請你確認" in cont["reply"]
    guard = agent.guard_check(cont)
    assert guard and "任務接著做：會改變狀態的是 第 2 步 改成 20" in guard["reason"] and "已經查到的" in guard["reason"], guard
    assert agent.run_tool(cont, approved=False).startswith("[DENIED]") and "exposure: 10" in read(cam)
    rep = agent.run_tool(cont, approved=True)
    assert rep.startswith("[PASS] 任務完成（2/2 步") and "exposure: 20" in read(cam), rep
    assert "## 計畫改過" in rep and "第 2 版：查詢的步驟做完了" in rep and "要回報給使用者的重點：exposure 修改前後" in rep, rep
    assert agent.run_tool(cont, approved=True).startswith("[ERROR] 沒有停下來等確認的任務"), "做完的任務不能再接著做"
    # 取消；新的使用者訊息之後不再自動接著問（任務還留著，同意了一樣接著做）
    check25 = dict(CHECK20, expect=r"exposure: 25")
    first25 = plan(first["items"][0], item("改成 25", "把 exposure 改成 25", ["file_ops"], True, check25))
    for k in range(2):
        fake = FakeTask([first25, plan(item("改成 25", "把 exposure 從 20 改成 25", ["file_ops"], True, check25))],
                        [step("scripts/cat_cmd.py", "config/cam.yaml"), done("exposure 現在是 20", [fact("exposure: 20")]),
                                             step("scripts/file_ops_cmd.py", "set config/cam.yaml exposure 25"), done("改好了")])
        ollama.chat = fake
        out = agent.run_tool(task(f"把 exposure 改成 25（第 {k} 次）"))
        assert out.startswith("[PASS] ⏸️ 任務"), out
        if k == 0:
            assert agent.run_tool({"action": {"command": "scripts/task_run_cmd.py", "args": "--cancel"}}).startswith("[PASS] 任務取消了")
            assert agent.take_task_continuation() is None and agent.task_job["status"] == "cancelled"
        else:
            note = agent.end_plan_for_new_task()
            assert note and "還留著" in note and agent.take_task_continuation() is None, note
            rep = agent.run_tool({"action": {"command": "scripts/task_run_cmd.py", "args": "--continue"}}, approved=True)
            assert rep.startswith("[PASS] 任務完成") and "exposure: 25" in read(cam), rep


# ---------------------------------------------------------------- worker 的規則
def t_worker_rules(agent, ollama, tmp, home):
    agent.guard_enabled = False                       # 確認關卡關掉：計畫裡要改的開始時就都核准（不停下來）
    p = plan(item("查狀態", "看 cam_driver 的設定", ["view_file"]),
             item("寫紀錄", "在 notes/out.txt 寫入 hello world", ["file_ops"], True, {"skill": "view_file", "args": "notes/out.txt", "expect": "world"}),
             item("重新啟動", "重新啟動 cam_driver", ["docker_ctl"]))
    fake = FakeTask([p], [
        # 第 1 步（只查詢）：想重啟容器 → [DENIED]；沒執行任何技能就說做完 → 推回去一次；之後真的查了才算
        step("scripts/docker_ctl_cmd.py", "restart cam_driver"), done("沒辦法重啟"), step("scripts/cat_cmd.py", "config/cam.yaml"),
        done("cam 的設定在 config/cam.yaml"),
        # 第 2 步：寫錯內容 → 檢查沒過 → 換 worker 重試 → 還是錯 → 標成「檢查沒過」、繼續
        step("scripts/file_ops_cmd.py", 'write notes/out.txt --text "hello"'), done("寫好了"),
        step("scripts/file_ops_cmd.py", 'write notes/out.txt --text "hello again"'), done("寫好了"),
        # 第 3 步（docker_ctl 重新啟動：目標寫了要改、兩用的技能 → 會改變狀態）：只看設定就回報
        step("scripts/cat_cmd.py", "config/cam.yaml"), done("已確認")])
    ollama.chat = fake
    rep = agent.run_tool(task("查 cam_driver、寫紀錄、重新啟動"))
    job = agent.task_last
    assert job["items"][2]["changes_state"], "目標寫了「重新啟動」、用的是兩用的 docker_ctl：算會改變狀態"
    w1 = fake.worker_msgs[1][-1]["content"]
    assert "[DENIED]" in w1 and "這一步只查詢" in w1, w1
    assert "你還沒有用任何技能" in fake.worker_msgs[2][-1]["content"], "沒用技能就說做完：推回去一次"
    assert rep.startswith("[PASS] 任務的步驟都做了") and "第 2 步做完之後的檢查沒有通過" in rep, rep
    assert "2. ⚠️ 檢查沒過 寫紀錄" in rep and "沒有「world」" in rep, rep
    retry = fake.worker_msgs[6][1]["content"]
    assert "【上一次做這一步沒有成功】你回報完成了，但做完之後的檢查沒有通過" in retry, retry
    assert job["items"][1]["attempts"] == 2 and job["items"][2]["status"] == "done", job["items"]
    # 這一步不能用的技能（計畫沒列、又不是每一步都能用的查詢技能）；worker 回報做不到（❌）
    p = plan(item("讀設定", "讀 config/missing.yaml", ["view_file"]), item("回報", "整理讀到的設定", ["view_file"]))
    fake = FakeTask([p, plan()], [step("scripts/file_ops_cmd.py", 'write x.txt --text "x"'), step("scripts/cat_cmd.py", "config/missing.yaml"),
                                  done("❌ 沒有完成：找不到 config/missing.yaml"),
                                  step("scripts/cat_cmd.py", "config/missing.yaml"), done("❌ 沒有完成：還是找不到")])
    ollama.chat = fake
    rep = agent.run_tool(task("讀 config/missing.yaml 再整理"))
    assert "這一步不能用 file_ops" in fake.worker_msgs[1][-1]["content"] and not os.path.exists(os.path.join(home, "x.txt"))
    assert rep.startswith("[ERROR] 任務沒有做完：第 1 步沒有完成（試了 2 次）") and "還是找不到" in rep, rep
    assert fake.plan_calls == 2, "失敗之後交回規劃 session 重排一次（這裡規劃不出新的步驟，照原本的停下來）"


def t_step_cap_wrapup(agent, ollama, tmp, home):
    """worker 用完步數：最後請它總結；做完了（而且真的用過技能）就算完成、交給檢查，沒做完才算失敗。"""
    from agent_core.config import TASK_WORKER_MAX_STEPS
    agent.guard_enabled = False
    p = plan(item("看設定", "看 config/cam.yaml", ["view_file"]), item("看目錄", "看 config", ["list_dir"]))
    acts = [("scripts/cat_cmd.py", "config/cam.yaml"), ("scripts/ls_cmd.py", "config"), ("scripts/ls_cmd.py", "."),
            ("scripts/cat_cmd.py", "./config/cam.yaml"), ("scripts/ls_cmd.py", "./config")]
    busy = [step(*acts[k % len(acts)]) for k in range(TASK_WORKER_MAX_STEPS)]   # 每個動作最多兩次（第三次會被當成卡住）
    fake = FakeTask([p], busy + [step("scripts/ls_cmd.py", "config"), done("一個檔案")],
                    wrapups=[{"done": True, "summary": "exposure 是 10", "facts": [fact("exposure: 10")]}])
    ollama.chat = fake
    rep = agent.run_tool(task("看設定再看目錄"))
    assert rep.startswith("[PASS] 任務完成（2/2 步") and "exposure 是 10" in rep, rep
    assert agent.task_last["items"][0]["steps"] == TASK_WORKER_MAX_STEPS + 1, agent.task_last["items"][0]["steps"]


# ---------------------------------------------------------------- 事實的核對
def t_fact_check(agent, ollama, tmp, home):
    agent.guard_enabled = False
    p = plan(item("看設定", "看 config/cam.yaml 的 exposure 與 fps", ["view_file"]), item("看目錄", "看 config", ["list_dir"]))
    fake = FakeTask([p], [
        step("scripts/cat_cmd.py", "config/cam.yaml"),
        done("exposure 是 10、fps 是 30", [fact("exposure: 10"), fact("fps 是 15"), fact("設定檔有 3 行", "999")]),
        step("scripts/ls_cmd.py", "config"), done("一個檔案", [fact("cam.yaml")])],
        fixes=[{"facts": [fact("exposure: 10"), fact("fps: 30"), fact("gain 是 4.5")], "summary": "exposure 是 10、fps 是 30"}])
    ollama.chat = fake
    rep = agent.run_tool(task("看相機設定與目錄"))
    ask = fake.fix_msgs[0][-1]["content"]
    assert "「15」在 #" in ask and "出處 #999 不是這個任務執行過的工具結果" in ask, ask
    it = agent.task_last["items"][0]
    assert [f["text"] for f in it["facts"]] == ["exposure: 10", "fps: 30"], it["facts"]
    assert len(it["dropped"]) == 1 and it["dropped"][0]["text"] == "gain 是 4.5", it["dropped"]
    assert re.search(r"fps: 30（#\d+）", rep) and "另外 1 條在引用的輸出裡找不到，拿掉了" in rep and "fps 是 15" not in rep, rep


def t_fact_refs_before(agent, ollama, tmp, home):
    """事實引用這個任務前面各步的工具結果（#編號）：讀回存檔的原文核對（以前只認這一步執行過的——只整理前面結果的步驟引用前面的 #，
    全部被當成找不到拿掉，報告寫「另外 N 條找不到」）；值不對、不是這個任務的編號照樣交回改、改不好就拿掉"""
    agent.guard_enabled = False
    p = plan(item("看設定", "看 config/cam.yaml 的 exposure 與 fps", ["view_file"]), item("整理", "整理前面看到的設定", []))
    fake = FakeTask([p], [
        step("scripts/cat_cmd.py", "config/cam.yaml"), done("exposure 是 10", [fact("exposure: 10")]),
        done("整理好了", [fact("exposure 是 10", "FIRST"), fact("fps 是 30", "FIRST"), fact("fps 是 60", "FIRST"), fact("gain 是 4", "999")])],
        fixes=[{"facts": [fact("exposure 是 10", "FIRST"), fact("fps 是 30", "FIRST"), fact("fps 是 60", "FIRST")], "summary": "整理好了"}])
    ollama.chat = fake
    rep = agent.run_tool(task("看相機設定並整理"))
    first = agent.task_last["items"][0]["calls"][0]["rid"]
    ask = fake.fix_msgs[0][-1]["content"]
    assert "「60」在 #" in ask and "出處 #999 不是這個任務執行過的工具結果（這一步的是 沒有；前面各步的是 #" in ask, ask
    assert "exposure 是 10" not in ask and "fps 是 30" not in ask, "引用前面步驟的、核對得到的不交回"
    it = agent.task_last["items"][1]
    assert [f["text"] for f in it["facts"]] == ["exposure 是 10", "fps 是 30"] and all(f["ref"] == str(first) for f in it["facts"]), it["facts"]
    assert [f["text"] for f in it["dropped"]] == ["fps 是 60"], it["dropped"]
    assert f"fps 是 30（#{first}）" in rep and "另外 1 條在引用的輸出裡找不到" in rep, rep


def t_goal_check(agent, ollama, tmp, home):
    """worker 回報「沒有完成」（而且這一步執行過工具）：對照這一步的目標問一次做到了沒有——做到了（查到的結果有問題也算）就算完成、
    摘要換成照實的、不重試，照查到的狀況重排剩下的步驟（問題可能讓剩下的步驟不夠用）；沒做到才照舊重試、重排；一個工具都沒用就說沒完成的不問"""
    agent.guard_enabled = False
    goal = "看 config/cam.yaml 找出 exposure 跟規定的 20 不一樣的原因"
    look = item("看目錄", "看 config 有哪些檔案", ["list_dir"])
    fake = FakeTask([plan(item("查原因", goal, ["view_file"]), look), plan(look)],
                    [step("scripts/cat_cmd.py", "config/cam.yaml"), done("❌ 沒有完成：已經查到原因，但問題還在（exposure 是 10）", [fact("exposure: 10")]),
                     step("scripts/ls_cmd.py", "config"), done("一個檔案", [fact("cam.yaml")])],
                    goals=[{"goal_met": True, "summary": "查到了：exposure 是 10，不是規定的 20（還沒改）"}])
    ollama.chat = fake
    rep = agent.run_tool(task("查相機的 exposure 為什麼跟規定不一樣，再看 config 有哪些檔案"))
    assert agent.task_last, rep
    it = agent.task_last["items"][0]
    assert rep.startswith("[PASS] 任務完成（2/2 步") and it["status"] == "done" and it["attempts"] == 1, rep
    # 查到的狀況有問題：照它重排剩下的步驟（不重試這一步；規劃看得到它查到的）
    assert fake.plan_calls == 2 and "第 2 版：第 1 步「查原因」做完了，查到的狀況：查到了：exposure 是 10" in rep, rep
    assert "查到了：exposure 是 10" in fake.plan_msgs[1][1]["content"], fake.plan_msgs[1][1]["content"][-600:]
    assert it["summary"] == "查到了：exposure 是 10，不是規定的 20（還沒改）" and [f["text"] for f in it["facts"]] == ["exposure: 10"], it
    ask = fake.goal_msgs[0][-1]["content"]
    assert f"目標：{goal}" in ask and "問題還在、修不了，不算沒做到" in ask, ask
    calls = [json.loads(l) for l in open(os.path.join(job_dir(agent, agent.task_last), "calls.jsonl"), encoding="utf-8")]
    assert any(c.get("kind") == "worker_goal_check" for c in calls), "這一次問的也記在 calls.jsonl"
    # 重排出要改的步驟：照查到的事實重排過了，停下來確認之前不再重排一次（重排的次數留給後面的失敗）
    change = item("改成 20", "把 config/cam.yaml 的 exposure 改成 20", ["file_ops"], True, CHECK20)
    fake = FakeTask([plan(item("查原因", goal, ["view_file"]), look), plan(change)],
                    [step("scripts/cat_cmd.py", "config/cam.yaml"), done("❌ 沒有完成：查到了，exposure 是 10", [fact("exposure: 10")])],
                    goals=[{"goal_met": True, "summary": "查到了：exposure 是 10"}])
    ollama.chat = fake
    rep = agent.run_tool(task("查相機的 exposure 為什麼跟規定不一樣，需要的話改好"))
    paused = agent._task_find(agent.task_pending_approval)
    assert rep.startswith("[PASS] ⏸️ 任務") and fake.plan_calls == 2 and paused and paused["replans"] == 1, (rep[:160], fake.plan_calls)
    assert [p["why"][:12] for p in paused["plans"]] == ["第一版", "第 1 步「查原因」做完了"[:12]], paused["plans"]
    agent.run_tool({"action": {"command": "scripts/task_run_cmd.py", "args": "--cancel"}})
    # 沒做到：照舊重試（第二個 worker），還是沒做到就重排；重排不出新的步驟＝任務沒做完
    fake = FakeTask([plan(item("查原因", goal, ["view_file"]), look)],
                    [step("scripts/cat_cmd.py", "config/cam.yaml"), done("❌ 沒有完成：找不到 exposure"),
                     step("scripts/cat_cmd.py", "config/cam.yaml"), done("❌ 沒有完成：還是找不到")],
                    goals=[{"goal_met": False, "summary": "找不到"}, {"goal_met": False, "summary": "還是找不到"}])
    ollama.chat = fake
    rep = agent.run_tool(task("查相機的 exposure 為什麼跟規定不一樣，再看 config（再一次）"))
    it = agent.task_last["items"][0]
    assert it["attempts"] == 2 and len(fake.goal_msgs) == 2 and rep.startswith("[ERROR] 任務沒有做完"), (it["attempts"], rep[:200])
    assert it["summary"] == "❌ 沒有完成：還是找不到", "沒做到：摘要照 worker 原本的回報"
    # 一個工具都沒用就說沒完成：不問
    fake = FakeTask([plan(item("整理", "整理前面的結果", []), look)], [done("❌ 沒有完成：沒有東西可以整理")] * 2)
    ollama.chat = fake
    agent.run_tool(task("整理一下，再看 config"))
    assert not fake.goal_msgs and agent.task_last["items"][0]["attempts"] == 2, agent.task_last["items"][0]


def t_check_error(agent, ollama, tmp, home):
    """做完之後的檢查回 [ERROR]（程式沒辦法用它確認）：對照目標問一次做到了沒有（只看系統記下的動作與檢查的輸出）——沒做到（worker 只建了
    目錄就說報告寫好了，檢查讀不到報告）跟檢查沒過一樣換 worker 帶著檢查的輸出重試；做到了（檢查自己寫錯：參數寫反）算完成、標明程式沒有
    驗證、不多跑 worker；問不出來當成沒做到，重試後還是沒做到就標成「檢查沒過」。以前檢查出錯一律算完成，任務報 [PASS]"""
    agent.guard_enabled = False
    look = item("看設定", "看 config/cam.yaml 的 exposure", ["view_file"])
    seen = [step("scripts/cat_cmd.py", "config/cam.yaml"), done("exposure 是 10", [fact("exposure: 10")])]
    write = item("寫報告", "把看到的 exposure 寫進 reports/cam.md", ["file_ops"], True,
                 {"skill": "view_file", "args": "reports/cam.md", "expect": "exposure"})
    fake = FakeTask([plan(look, write)],
                    seen + [step("scripts/file_ops_cmd.py", "mkdir reports"), done("報告寫好了"),
                            step("scripts/file_ops_cmd.py", 'write reports/cam.md --text "exposure: 10"'), done("寫好了")],
                    goals=[{"goal_met": False, "summary": "只建了 reports 目錄，沒有寫 reports/cam.md"}])
    ollama.chat = fake
    rep = agent.run_tool(task("看相機的 exposure，寫成報告"))
    it = agent.task_last["items"][1]
    assert rep.startswith("[PASS] 任務完成（2/2 步") and it["status"] == "done" and it["attempts"] == 2, (rep[:300], it)
    assert "exposure: 10" in read(os.path.join(home, "reports", "cam.md"))
    ask = fake.goal_msgs[0][-1]["content"]
    assert "目標：把看到的 exposure 寫進 reports/cam.md" in ask and "- file_ops mkdir reports → [PASS]" in ask, ask
    assert "view_file reports/cam.md（要看到「exposure」）→ 出錯了：\n[ERROR] 找不到檔案" in ask and "不是 worker 說的" in ask, ask
    retry = fake.worker_msgs[4][1]["content"]
    assert "【上一次做這一步沒有成功】你回報完成了，但做完之後的檢查：view_file reports/cam.md → 檢查出錯（[ERROR] 找不到檔案" in retry, retry
    assert "對照目標判斷還沒做到：只建了 reports 目錄" in retry, retry
    calls = [json.loads(l) for l in open(os.path.join(job_dir(agent, agent.task_last), "calls.jsonl"), encoding="utf-8")]
    judged = [c for c in calls if c.get("kind") == "check_error"]
    assert len(judged) == 1 and judged[0]["messages"][-1]["content"] == ask and judged[0]["item"] == 2, "問的與回答整份存檔"
    # 檢查自己寫錯（search_text 的關鍵字與路徑寫反）：做到了就算完成，不多跑 worker；報告寫明檢查出錯、程式沒有驗證
    note = item("寫紀錄", "在 notes/out.txt 寫入 hello", ["file_ops"], True, {"skill": "search_text", "args": "notes/out.txt hello", "expect": "hello"})
    fake = FakeTask([plan(look, note)],
                    seen + [step("scripts/file_ops_cmd.py", 'write notes/out.txt --text "hello"'), done("寫好了")],
                    goals=[{"goal_met": True, "summary": "write 的輸出顯示已寫入 notes/out.txt；檢查把關鍵字與路徑寫反了"}])
    ollama.chat = fake
    rep = agent.run_tool(task("看相機的 exposure，再寫一行紀錄"))
    it = agent.task_last["items"][1]
    assert rep.startswith("[PASS] 任務完成（2/2 步") and it["status"] == "done" and it["attempts"] == 1, (rep[:300], it)
    assert len(fake.goal_msgs) == 1 and len(fake.worker_msgs) == 4, "做到了：不多跑一個 worker"
    assert "檢查：search_text notes/out.txt hello → 檢查出錯（[ERROR] 找不到路徑：hello" in rep, rep
    assert "程式沒有驗證，對照目標判斷做到了：write 的輸出顯示已寫入" in rep, rep
    # 問不出來（回答是空的）當成沒做到：重試；第二次檢查還是出錯、還是沒做到 → 標成「檢查沒過」，不是完成
    lost = item("寫報告", "把看到的 exposure 寫進 reports/lost.md", ["file_ops"], True,
                {"skill": "view_file", "args": "reports/lost.md", "expect": "exposure"})
    fake = FakeTask([plan(look, lost)],
                    seen + [step("scripts/file_ops_cmd.py", "mkdir reports/tmp"), done("報告寫好了"),
                            step("scripts/ls_cmd.py", "reports"), done("報告已經寫好了")],
                    goals=[{}, {"goal_met": False, "summary": "reports/lost.md 還是不存在"}])
    ollama.chat = fake
    rep = agent.run_tool(task("看相機的 exposure，寫成另一份報告"))
    it = agent.task_last["items"][1]
    assert it["status"] == "unverified" and it["attempts"] == 2 and len(fake.goal_msgs) == 2, it
    assert rep.startswith("[PASS] 任務的步驟都做了") and "第 2 步做完之後的檢查沒有通過" in rep and "2. ⚠️ 檢查沒過 寫報告" in rep, rep
    assert "對照目標判斷還沒做到：reports/lost.md 還是不存在" in rep, rep
    assert "對照目標判斷還沒做到。先查清楚現在的狀態" in fake.worker_msgs[4][1]["content"], fake.worker_msgs[4][1]["content"]


# ---------------------------------------------------------------- 失敗：自動模式重排、Plan 模式不重排
def t_failure_replan(agent, ollama, tmp, home):
    agent.guard_enabled = False
    p = plan(item("讀設定", "讀 config/missing.yaml", ["view_file"]), item("整理", "整理讀到的設定", ["view_file"]))
    again = plan(item("找設定檔", "列出 config 目錄，找相機的設定檔", ["list_dir"]))
    steps = [step("scripts/cat_cmd.py", "config/missing.yaml"), done("❌ 沒有完成：找不到"),
             step("scripts/cat_cmd.py", "config/missing.yaml"), done("❌ 沒有完成：還是找不到")]
    fake = FakeTask([p, again], steps + [step("scripts/ls_cmd.py", "config"), done("設定檔是 config/cam.yaml", [fact("cam.yaml")])])
    ollama.chat = fake
    rep = agent.run_tool(task("讀相機的設定並整理"))
    assert rep.startswith("[PASS] 任務完成") and "1. ↩️ 沒做成、重排了 讀設定" in rep, rep
    assert "目錄列表" in fake.worker_msgs[-1][-1]["content"], "list_dir（ls_cmd.py）在 list_dir 的步驟裡用得了"
    assert [f["text"] for f in agent.task_last["items"][1]["facts"]] == ["cam.yaml"], agent.task_last["items"][1]
    assert "第 2 版：第 1 步「讀設定」沒有完成：❌ 沒有完成：還是找不到" in rep and "2. ✅ 找設定檔" in rep, rep
    replan_prompt = fake.plan_msgs[1][1]["content"]
    assert "第 1 步「讀設定」沒有做成，重排了剩下的步驟：❌ 沒有完成：還是找不到" in replan_prompt, replan_prompt[-900:]
    # Plan 模式：使用者核准的就是這一份，不重排、停下來
    fake = FakeTask([p], list(steps))
    ollama.chat = fake
    agent.plan_start_draft("讀相機的設定並整理")
    assert agent.plan_handle_input("y")[0] == "approved"
    rep = agent.run_tool(agent.take_task_continuation())
    assert rep.startswith("[ERROR] 任務沒有做完：第 1 步沒有完成") and fake.plan_calls == 1, rep


# ---------------------------------------------------------------- 程式看得出的前提
def t_broken_plans(agent, ollama, tmp, home):
    """修一次還是有做不了的步驟（要改變狀態卻沒有技能、列的技能都不存在、工作流的參數不對）：不執行、回錯誤；要寫檔卻沒列 file_ops 交回修；
    Plan 模式的草稿有做不了的步驟時不能核准"""
    nothing = item("派工作包", "派 p0 到 p2 的工作包給 amr_07", [], True)
    ghost = item("看設定", "看 config/cam.yaml", ["no_such_skill"])
    fake = FakeTask([plan(nothing, ghost), plan(nothing, ghost)], [done("不該執行")])
    ollama.chat = fake
    out = agent.run_tool(task("派工作包給 amr_07 再看設定"), approved=True)
    assert out.startswith("[ERROR] 規劃出來的計畫有做不了的步驟（第 1、2 步") and fake.plan_calls == 2, out
    assert not fake.worker_msgs, "做不了的計畫：一步都不執行"
    # 經過確認關卡（評測、CLI、Web 都先問關卡）：關卡規劃失敗 → 不用確認；接著 run_tool 的關卡不再規劃一次（以前第二次規劃出第一步就要改的
    # 計畫，被擋成 [DENIED]），task_run 回報第一次的錯誤
    good = item("改成 20", "把 config/cam.yaml 的 exposure 改成 20", ["file_ops"], True, CHECK20)
    fake = FakeTask([plan(nothing, ghost), plan(nothing, ghost), plan(good, item("看", "看 config/cam.yaml", ["view_file"]))])
    ollama.chat = fake
    act = task("派工作包給 amr_07 再看設定（第二次）")
    assert agent.guard_check(act) is None and fake.plan_calls == 2
    out = agent.run_tool(act)
    assert out.startswith("[ERROR] 規劃出來的計畫有做不了的步驟") and fake.plan_calls == 2, (out[:120], fake.plan_calls)
    write = item("記紀錄", "在 notes/log.md 記一筆結果", ["view_file"], True)
    fake = FakeTask([plan(item("看設定", "看 config/cam.yaml", ["view_file"]), write)] * 2)
    ollama.chat = fake
    agent.task_plan("看設定再記一筆")
    assert "第 2 步要寫進 notes/log.md，skills 要列 file_ops" in fake.plan_msgs[1][1]["content"], fake.plan_msgs[1][1]["content"][-500:]
    fake = FakeTask([plan(item("看設定", "看 config/cam.yaml", ["view_file"]), nothing)])
    ollama.chat = fake
    agent.plan_start_draft("看設定再派工作包")
    outcome, msg = agent.plan_handle_input("y")
    assert outcome == "edited" and msg.startswith("第 2 步做不了") and agent.plan_status() == "draft", msg
    assert agent.plan_edit_command("/plan del 2")[0] and agent.plan_handle_input("y")[0] == "approved"


def t_preconditions(agent, ollama, tmp, home):
    agent._task_containers = lambda: ({"cam_driver": {"running": False, "status": "Exited (1) 2 minutes ago"},
                                       "db": {"running": True, "status": "Up 3 hours"}}, None)
    restart = item("重新啟動", "重新啟動 cam_driver", ["docker_ctl"], True, {"skill": "docker_ctl", "args": "status cam_driver", "expect": "Up"})
    look = item("看設定", "在 cam_driver 裡看 /etc/camera.conf 的 fps", ["docker_runcmd"])
    fake = FakeTask([plan(look, restart), plan(restart, look)])
    ollama.chat = fake
    job, err = agent.task_plan("cam_driver 停了，重新啟動並確認 /etc/camera.conf 的 fps")
    assert err is None and [it["title"] for it in job["items"]] == ["重新啟動", "看設定"], (err, job and job["items"])
    first, fix = fake.plan_msgs[0][1]["content"], fake.plan_msgs[1][1]["content"]
    assert "容器（名稱：狀態）：cam_driver：Exited (1) 2 minutes ago；db：Up 3 hours" in first, first[-600:]
    assert "第 1 步要在 cam_driver 裡面做，但 cam_driver 現在沒有在跑（Exited (1) 2 minutes ago），第 2 步才啟動它" in fix, fix[-800:]
    fake = FakeTask([plan(look, item("整理", "整理結果", ["view_file"]))] * 2)
    ollama.chat = fake
    job, _ = agent.task_plan("cam_driver 的 fps 是多少")
    assert "要進容器得先啟動（使用者要求才可以）" in job["issues"][0], job["issues"]
    agent._task_containers = lambda: ({"cam_driver": {"running": True, "status": "Up 1 minute"}}, None)
    fake = FakeTask([plan(look, restart)])
    ollama.chat = fake
    job, _ = agent.task_plan("看 cam_driver 的 fps 再重新啟動")
    assert fake.plan_calls == 1 and not job["issues"], "容器在跑：沒有問題，不用修"
    # 使用者提到手冊：要改之前先讀那份文件
    change = item("改成 20", "把 config/cam.yaml 的 exposure 改成 20", ["file_ops"], True, CHECK20)
    read_doc = item("讀手冊", "找到並讀作業手冊", ["find_file", "view_file"])
    fake = FakeTask([plan(change, item("確認", "再看一次", ["view_file"])), plan(read_doc, change)])
    ollama.chat = fake
    job, _ = agent.task_plan("照作業手冊把 config/cam.yaml 的 exposure 改成 20")
    assert "使用者提到「手冊」：先排一步找到並讀那份文件" in fake.plan_msgs[1][1]["content"] and not job["issues"], job["issues"]


# ---------------------------------------------------------------- 工作流的步驟
def t_workflow_items(agent, ollama, tmp, home):
    wf_item = item("附加紀錄", "在 notes/a.md 附加 hello", [], workflow="note_append", wargs="file=notes/a.md text=hello")
    p = plan(wf_item, item("看目錄", "看 notes", ["list_dir"]))
    fake = FakeTask([p], [step("scripts/ls_cmd.py", "notes"), done("notes 有 a.md", [fact("a.md")])])
    ollama.chat = fake
    act = task("在 notes/a.md 記一行 hello，再看 notes")
    guard = agent.guard_check(act)
    assert guard and "工作流 note_append file=notes/a.md text=hello" in guard["reason"], guard
    it = agent.task_job["items"][0]
    assert it["workflow"] == "note_append" and it["changes_state"] and it["skills"] == ["file_ops", "view_file"], it
    rep = agent.run_tool(act, approved=True)
    assert rep.startswith("[PASS] 任務完成（2/2 步") and "hello" in read(os.path.join(home, "notes", "a.md")), rep
    assert "1. ✅ 附加紀錄：[PASS] 工作流 note_append（附加一行紀錄）完成" in rep and re.search(r"附加到 notes/a\.md：\[PASS\] 已附加.*（#\d+）", rep), rep
    assert "text=…：要附加的字" in fake.plan_msgs[0][1]["content"], "規劃看得到工作流每個參數的說明（格式、例子）"
    assert agent.task_last["items"][0]["workflow_job"], "工作流的紀錄在 workflow_jobs"
    # 不能放進計畫的：有【確認】、不存在、參數不對；整件事就是一個工作流 → 直接用 workflow_run
    bad = plan(item("有確認", "x", [], workflow="confirm_test", wargs="file=notes/a.md text=x"),
               item("沒有這個", "x", [], workflow="no_such_wf"), item("少參數", "x", [], workflow="note_append", wargs="file=notes/a.md"))
    fake = FakeTask([bad, bad])
    ollama.chat = fake
    job, err = agent.task_plan("測試不合法的工作流步驟")
    fix = fake.plan_msgs[1][1]["content"]
    assert "工作流 confirm_test 有【確認】" in fix and "工作流 no_such_wf 不存在" in fix and "少了必填的：text" in fix, fix[-900:]
    assert "confirm_test" not in fake.plan_msgs[0][1]["content"], "有【確認】的工作流不列給規劃看"
    fake = FakeTask([plan(wf_item)])
    ollama.chat = fake
    out = agent.run_tool(task("在 notes/a.md 記一行 hello"))
    assert out.startswith("[ERROR] 這個任務正好是工作流 note_append") and "workflow_run note_append file=notes/a.md text=hello" in out, out
    # 規劃常見的寫法：工作流的名稱寫在 skills、參數用逗號隔開 → 程式整理成工作流的步驟；目標寫了工作流卻沒填 workflow → 交回修
    loose = item("附加紀錄", "在 notes/b.md 附加 hi", ["note_append"], wargs="file=notes/b.md, text=hi,")
    named = item("用工作流記", "用 note_append 工作流在 notes/c.md 記一行", ["file_ops"], True)
    fake = FakeTask([plan(loose, named), plan(loose, item("記一行", "在 notes/c.md 記一行 x", ["file_ops"], True))])
    ollama.chat = fake
    job, err = agent.task_plan("在 notes 記兩行")
    it = job["items"][0]
    assert it["workflow"] == "note_append" and it["inputs"]["file"] == "notes/b.md" and it["inputs"]["text"] == "hi", it
    from agent_core.task_engine import _clean_wf_args
    assert _clean_wf_args("file=notes/d.md text=hello world, x") == "file=notes/d.md 'text=hello world x'", "值有空白沒加引號：接起來"
    assert "目標寫了工作流 note_append，但沒有填 workflow" in fake.plan_msgs[1][1]["content"], fake.plan_msgs[1][1]["content"][-600:]


# ---------------------------------------------------------------- Plan 模式
def t_plan_mode(agent, ollama, tmp, home):
    cam = os.path.join(home, "config", "cam.yaml")
    draft = plan(item("看現在的值", "看 config/cam.yaml 的 exposure", ["view_file"]),
                 item("改成 20", "把 config/cam.yaml 的 exposure 從 10 改成 20", ["file_ops"], True, CHECK20))
    fake = FakeTask([draft], [step("scripts/cat_cmd.py", "config/cam.yaml"), done("exposure 是 10", [fact("exposure: 10")]),
                              step("scripts/file_ops_cmd.py", "set config/cam.yaml exposure 20"), done("改好了"),
                              step("scripts/file_ops_cmd.py", 'append notes/log.md --text "改了 exposure"'), done("記好了")],
                    ops=[{"ops": [{"op": "edit", "step": 2, "to": 0, "skill": "list_dir", "goal": "看 config 目錄"}]}])
    ollama.chat = fake
    n0 = len(agent.messages)
    view = agent.plan_start_draft("把 exposure 改成 20")
    assert agent.plan_status() == "draft" and agent.plan["mode"] == "plan" and "1. 看現在的值（只查詢；技能：view_file）" in view, view
    assert "y＝核准並執行" in view and len(agent.messages) == n0, "草稿不進主對話"
    ok, msg = agent.plan_edit_command("/plan add file_ops：在 notes/log.md 附加一行「改了 exposure」")
    assert ok and agent.plan["items"][2]["changes_state"] and agent.plan["items"][2]["skills"] == ["file_ops"], agent.plan["items"]
    assert agent.plan_edit_command("/plan move 3 1")[0] and agent.plan["items"][0]["skills"] == ["file_ops"]
    assert agent.plan_edit_command("/plan move 1 3")[0] and [it["n"] for it in agent.plan["items"]] == [1, 2, 3]
    assert agent.plan_edit_command("/plan add note_append：file=notes/b.md text=hi")[0] and agent.plan["items"][3]["workflow"] == "note_append"
    assert agent.plan_edit_command("/plan del 4")[0] and len(agent.plan["items"]) == 3
    outcome, msg = agent.plan_handle_input("第二步改成看 config 目錄")
    assert outcome == "edited" and agent.plan["items"][1]["skills"] == ["list_dir"] and "改第 2 步" in msg, msg
    assert agent.plan_handle_input("/plan edit 2 file_ops：把 config/cam.yaml 的 exposure 從 10 改成 20")[0] == "edited"
    agent.plan["items"][1]["check"] = dict(CHECK20)
    outcome, msg = agent.plan_handle_input("y")
    assert outcome == "approved" and agent.plan is None and agent.messages[-1] == {"role": "user", "content": "把 exposure 改成 20"}, msg
    cont = agent.take_task_continuation()
    assert cont and cont["reply"] == "照核准的計畫執行。" and agent.guard_check(cont) is None, "Plan 模式核准過：不再確認"
    rep = agent.run_tool(cont)
    assert rep.startswith("[PASS] 任務完成（3/3 步") and "exposure: 20" in read(cam) and fake.plan_calls == 1, rep
    assert "改了 exposure" in read(os.path.join(home, "notes", "log.md")) and "## 計畫改過" not in rep, "照核准的計畫做、不重排"
    # 取消；/plan add 從空的草稿開始
    fake = FakeTask([draft])
    ollama.chat = fake
    agent.plan_start_draft("把 exposure 改成 30")
    jid = agent.plan["id"]
    assert agent.plan_handle_input("n")[0] == "rejected" and agent.plan is None
    assert json.load(open(os.path.join(agent.script_dir, "logs", "task_jobs", jid, "job.json")))["status"] == "cancelled"
    assert agent.plan_edit_command("/plan edit 1 view_file：看")[1].startswith("目前沒有草稿")
    ok, msg = agent.plan_edit_command("/plan add view_file：看 config/cam.yaml")
    assert ok and agent.plan_status() == "draft" and agent.plan["task"] == "（使用者自己列的計畫）"
    assert agent.plan_handle_input("y")[0] == "approved" and agent.messages[-1]["content"].startswith("照我列的計畫做")


# ---------------------------------------------------------------- 存檔的保留、/clear
def t_keep_and_clear(agent, ollama, tmp, home):
    from agent_core import task_engine
    task_engine.TASK_JOBS_KEEP = 2
    p = plan(item("看設定", "看 config/cam.yaml", ["view_file"]), item("看目錄", "看 config", ["list_dir"]))
    for k in range(4):
        ollama.chat = FakeTask([p])
        agent.task_plan(f"看設定再看目錄（第 {k} 次）")
    ids = os.listdir(os.path.join(agent.script_dir, "logs", "task_jobs"))
    assert len(ids) == 2, ids
    agent.task_pending_approval = "x"
    agent.reset_conversation()
    assert agent.task_job is None and agent.task_pending_approval is None
    out = agent.run_tool({"action": {"command": "scripts/task_run_cmd.py", "args": "--continue"}}, approved=True)
    assert out.startswith("[ERROR] 沒有停下來等確認的任務"), out
    assert agent.run_tool({"action": {"command": "scripts/task_run_cmd.py", "args": ""}}).startswith("[ERROR] task_run 需要任務描述")
    assert agent.run_tool(task("ab")).startswith("[ERROR] task_run 需要任務描述")
    out = agent.run_tool({"action": {"command": "scripts/task_run_cmd.py", "args": '--profile nope "看設定再看目錄"'}})
    assert out.startswith("[ERROR] 沒有任務類型 nope：現有的是 ops"), out


def main():
    results = []
    for name, fn in [("規劃的程式檢查與修正；第一步就要改：確認關卡是整份計畫、核准才執行；事實附 #編號；報告不再提煉；存檔", t_first_step_changes),
                     ("先查再確認：開頭的查詢直接做 → 照事實重排 → 停下來 → harness 接著問 → 核准才改；取消；新訊息後不再自動問", t_survey_then_confirm),
                     ("worker：沒核准的 [DENIED]、沒用技能推回去、不能用的技能、檢查沒過重試後標成「檢查沒過」、做不到（❌）", t_worker_rules),
                     ("worker 用完步數時請它總結：做完了就算完成（交給檢查）", t_step_cap_wrapup),
                     ("事實的核對：名稱與數值要在引用的輸出裡；出處要是這個任務的；交回改一次，還是不行就拿掉", t_fact_check),
                     ("事實引用前面各步的工具結果：讀回存檔核對（只整理前面結果的步驟不會被當成找不到）", t_fact_refs_before),
                     ("worker 說沒有完成：對照目標問一次做到了沒有（查到的結果有問題也算做到，照它重排剩下的）；沒做到才重試、重排", t_goal_check),
                     ("檢查出錯：對照目標問一次（只看系統記下的動作）；沒做到換 worker 重試，做到了算完成、標明沒有驗證；問不出來當成沒做到", t_check_error),
                     ("失敗：自動模式重排剩下的步驟（那一步標成重排了）；Plan 模式不重排", t_failure_replan),
                     ("前提：停著的容器排在啟動之前、容器停著卻要進去、使用者提到手冊卻沒先讀；規劃看得到容器的狀態", t_preconditions),
                     ("做不了的計畫不執行（要改卻沒有技能、技能都不存在）；要寫檔卻沒列 file_ops 交回修；Plan 模式擋核准", t_broken_plans),
                     ("工作流的步驟：交給工作流的執行器；有【確認】、不存在、參數不對的不能放；整件事就是一個工作流時交回主對話；名稱寫在 skills、參數用逗號的照整理", t_workflow_items),
                     ("Plan 模式：任務引擎規劃草稿、/plan 指令、用說的改、核准後照計畫做（不再確認、不重排）、取消、自己列", t_plan_mode),
                     ("存檔只留最近幾次；/clear 清掉等確認的任務；參數錯誤、沒有這個類型", t_keep_and_clear)]:
        scenario(name, fn, results)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
