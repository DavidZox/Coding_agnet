"""coding orchestrator 的離線自我測試：用假的 ollama.chat（照劇本回答），幾秒鐘跑完，不需要 Ollama。

    python3 evals/coding_selftest.py

測的是 harness 本身的流程與保證（不是模型的能力；模型的能力用 run_coding_evals.py 量）：
規劃的修正（路徑補目錄、拿掉只跑驗證的項目、參考檔案）、核准前不改檔、用說的改計畫、直接編輯計畫、worker 的決定與內容通道、
驗證（失敗交還 worker、換 worker 重試、停下來問使用者、跳過）、整體驗證、報告存檔、還原、停止。
每一個情境都在臨時目錄複製一份專案與 fixture，不碰正式的 logs/。"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
GOOD_STORE_ADDITION = '''
    def restock_below(self, threshold, amount):
        """qty < threshold 的品項加上 amount，回傳補貨品項名稱的排序清單。"""
        names = sorted(n for n, i in self.items.items() if i.qty < threshold)
        for n in names:
            self.items[n].qty += amount
        return names
'''
TEST_ADDITION = '''

def test_restock_below(inv):
    assert inv.restock_below(2, 3) == ["pear"]
    assert inv.items["pear"].qty == 4
'''


class FakeModel:
    """照劇本回答的假模型：依 format（哪一種 session）與 worker 的步數決定回什麼。"""

    def __init__(self, worker_script, content_script):
        self.worker_script = list(worker_script)    # 每次 worker 決定時依序取一個
        self.content_script = list(content_script)  # 每次內容通道依序取一個（callable(檔案內容) → 回覆文字）
        self.calls = []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = sorted((format or {}).get("properties", {})) if isinstance(format, dict) else []
        self.calls.append(props)
        if "files_to_read" in props:
            data = {"understanding": "在 Inventory 新增 restock_below 並加測試", "files_to_read": ["store.py", "tests/test_store.py"],
                    "questions": []}
        elif "items" in props:
            data = {"summary": "在 store.py 加方法，再加測試", "final_verify": "python -m pytest -q", "risks": [],
                    "items": [
                        {"title": "Inventory 新增 restock_below", "goal": "在 Inventory 新增 restock_below(threshold, amount)，並加測試",
                         "files": ["store.py", "tests/test_store.py"], "context_files": [], "verify": "python -m pytest -q tests/test_store.py"},
                        {"title": "Final Verification", "goal": "執行所有測試確認通過", "files": [], "context_files": [], "verify": "python3 -m pytest -q"},
                    ]}
        elif "ops" in props:
            data = {"ops": [{"op": "edit", "step": 1, "to": 0, "title": "Inventory 新增 restock_below（改過）", "goal": "", "files": [],
                             "verify": ""}], "final_verify": "python3 -m pytest -q"}
        elif "action" in props:
            data = self.worker_script.pop(0) if self.worker_script else {"thought": "做完了", "reply": "完成", "action": None}
        else:   # 內容通道（沒有 format）
            text = messages[-1]["content"]
            fn = self.content_script.pop(0) if self.content_script else (lambda t: "```python\nx = 1\n```")
            return {"message": {"content": fn(text)}, "prompt_eval_count": 100, "eval_count": 50}
        return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 100, "eval_count": 20}


def current_file(text, marker="（目前的完整內容，沒有行號）：\n```python\n"):
    i = text.find(marker)
    j = text.find("\n```", i + len(marker))
    return text[i + len(marker):j] if i >= 0 else ""


def edit(cmd, path):
    return {"thought": f"修改 {path}", "reply": f"修改 {path}", "action": {"command": cmd, "args": path}}


DONE = {"thought": "做完了", "reply": "新增了 restock_below 與測試", "action": None}


def make_env():
    tmp = tempfile.mkdtemp(prefix="coding_selftest_")
    for item in ["agent_core", "skills_system", "coding_agents", "context_modes", "AGENT.md", "Memory.md"]:
        src = os.path.join(PROJECT, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, os.path.join(tmp, item))
    ws = os.path.join(tmp, "workspace")
    shutil.copytree(os.path.join(HERE, "coding_fixtures", "inventory_app"), ws, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp, ws


def wait(job, statuses, timeout=60):
    t0 = time.time()
    while job["status"] not in statuses:
        if time.time() - t0 > timeout:
            raise AssertionError(f"等不到狀態 {statuses}（目前 {job['status']}）")
        time.sleep(0.05)


def scenario(name, fn, results):
    tmp, ws = make_env()
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
        orch = agent.enable_coding()
        fn(agent, orch, ws, ollama)
        results.append((name, True, ""))
        print(f"✅ {name}")
    except Exception as e:
        import traceback
        results.append((name, False, traceback.format_exc()))
        print(f"❌ {name}：{e}")
    finally:
        try:
            orch.stop_service()
        except Exception:
            pass
        os.chdir(cwd)
        sys.path.remove(tmp)
        shutil.rmtree(tmp, ignore_errors=True)


def t_happy_path(agent, orch, ws, ollama):
    original = open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read()
    fake = FakeModel([edit("scripts/code_edit_cmd.py", "inventory/store.py"), edit("code_edit", "tests/test_store.py"), DONE],
                     [lambda t: "```python\n" + current_file(t).rstrip("\n") + "\n" + GOOD_STORE_ADDITION + "```",
                      lambda t: "```python\n" + current_file(t).rstrip("\n") + TEST_ADDITION + "```"])
    ollama.chat = fake
    with open(os.path.join(ws, "AGENTS.md"), "w", encoding="utf-8") as f:
        f.write("# 開發規範\n錯誤訊息一律用英文。\n")
    job, err = orch.submit("在 Inventory 新增 restock_below(threshold, amount)，並加測試", ws, "selftest")
    assert not err, err
    wait(job, {"awaiting_approval", "failed"})
    assert job["status"] == "awaiting_approval", job.get("error")
    items = job["items"]
    assert len(items) == 1, f"只跑驗證的項目應該被拿掉：{[i['title'] for i in items]}"
    assert items[0]["files"] == ["inventory/store.py", "tests/test_store.py"], f"路徑沒有補上目錄：{items[0]['files']}"
    assert items[0]["verify"].startswith("python3 "), f"python 應換成 python3：{items[0]['verify']}"
    assert any("改成專案裡實際的" in w for w in job["warnings"]), job["warnings"]
    assert open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read() == original, "核准前不應該改檔"
    note = orch.revise(job["id"], "第一項的標題加上（改過）")
    assert "（改過）" in job["items"][0]["title"], note
    orch.edit_item(job["id"], 1, {"verify": "python3 -m pytest -q tests/test_store.py"})
    orch.approve(job["id"])
    wait(job, {"done", "partial", "failed"})
    assert job["status"] == "done", (job["status"], job.get("error"), [(i["status"], i["summary"]) for i in job["items"]])
    text = open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read()
    assert "def restock_below" in text
    assert job["final_ok"] is True and job["report_id"], job.get("final_output")
    assert "restock_below" in orch.diff_text(job)
    assert os.path.exists(os.path.join(orch.job_dir(job["id"]), "workers", "item1_try1.md"))
    line = agent.build_state_tail()
    assert f"job #{job['id']}" in line and f"報告存檔 #{job['report_id']}" in line, line
    brief = open(os.path.join(orch.job_dir(job["id"]), "workers", "item1_try1.md"), encoding="utf-8").read()
    assert "專案的開發規範（AGENTS.md" in brief and "錯誤訊息一律用英文" in brief, "worker 的任務說明應該附上 AGENTS.md"
    test_orig = open(os.path.join(HERE, "coding_fixtures", "inventory_app", "tests", "test_store.py"), encoding="utf-8").read()
    orch.revert_file(job["id"], "tests/test_store.py")
    assert open(os.path.join(ws, "tests/test_store.py"), encoding="utf-8").read() == test_orig, "單一檔案還原失敗"
    assert "def restock_below" in open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read(), "其他檔案不該被還原"
    msg = orch.revert(job["id"])
    assert open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read() == original, msg
    assert job["status"] == "reverted"


def t_verify_fail_then_skip(agent, orch, ws, ollama):
    broken = lambda t: "```python\n" + current_file(t).rstrip("\n") + "\n\n    def restock_below(self, threshold, amount):\n        return undefined_name\n```"
    script = []
    for _ in range(2):   # 兩個 worker，各試 3 次驗證
        script += [edit("scripts/code_edit_cmd.py", "inventory/store.py"), DONE, DONE, DONE]
    ollama.chat = FakeModel(script, [broken] * 10)
    orch.on_fail = "ask"
    job, _ = orch.submit("在 Inventory 新增 restock_below", ws, "selftest")
    wait(job, {"awaiting_approval"})
    orch.approve(job["id"])
    wait(job, {"needs_attention", "done", "partial", "failed"})
    assert job["status"] == "needs_attention", job["status"]
    it = job["items"][0]
    assert it["attempts"] == 2, it["attempts"]
    evs = [e for e in orch.events(job["id"]) if e["type"] == "verify" and not e.get("ok")]
    assert evs and "未定義的名稱 'undefined_name'" in (evs[0].get("detail") or ""), evs[:1]
    orch.decide(job["id"], "skip")
    wait(job, {"done", "partial", "failed", "cancelled"})
    assert job["status"] == "partial", job["status"]
    assert job["items"][0]["status"] == "skipped"


def t_cancel_while_waiting(agent, orch, ws, ollama):
    ollama.chat = FakeModel([], [])
    job, _ = orch.submit("在 Inventory 新增 restock_below", ws, "selftest")
    wait(job, {"awaiting_approval"})
    orch.cancel(job["id"])
    wait(job, {"cancelled"})
    assert not os.path.exists(os.path.join(orch.backup_dir(job), "manifest.json")), "取消的 job 不應該改過檔案"


def t_inbox_and_scripts(agent, orch, ws, ollama):
    """code_job_send 寫收件匣 → 服務接手；code_job_status／code_job_cancel 讀寫檔案。"""
    import subprocess
    ollama.chat = FakeModel([], [])
    scripts = os.path.join(agent.script_dir, "skills_system", "scripts")
    out = subprocess.run([sys.executable, os.path.join(scripts, "code_job_send_cmd.py"), "--workspace", ws,
                          "在 Inventory 新增 restock_below 並加測試"], capture_output=True, text=True, timeout=30).stdout
    assert out.startswith("[PASS] 已交給 coding orchestrator：job #"), out
    job = orch.latest()
    wait(job, {"awaiting_approval"})
    out = subprocess.run([sys.executable, os.path.join(scripts, "code_job_status_cmd.py"), str(job["id"])],
                         capture_output=True, text=True, timeout=30).stdout
    assert "等使用者核准計畫" in out, out
    out = subprocess.run([sys.executable, os.path.join(scripts, "code_job_cancel_cmd.py"), str(job["id"])],
                         capture_output=True, text=True, timeout=30).stdout
    assert out.startswith("[PASS] 已要求停止"), out
    wait(job, {"cancelled"}, timeout=10)


def t_resume_after_restart(agent, orch, ws, ollama):
    """程式重新啟動時還在執行的 job：標成中斷；接著做時只做沒做完的項目。"""
    from agent_core.coding_job import CodingOrchestrator
    fake = FakeModel([edit("scripts/code_edit_cmd.py", "inventory/store.py"), DONE],
                     [lambda t: "```python\n" + current_file(t).rstrip("\n") + "\n" + GOOD_STORE_ADDITION + "```"])
    ollama.chat = fake
    orch.stop_service()
    jid = 7
    d = orch.job_dir(jid)
    os.makedirs(os.path.join(d, "backup"), exist_ok=True)
    item1 = orch.new_item(1, "已經做完的項目", "（之前做完的）", ["README.md"], [], "")
    item1.update(status="done", attempts=1, steps=5, summary="之前做完的")
    item2 = orch.new_item(2, "Inventory 新增 restock_below", "在 Inventory 新增 restock_below(threshold, amount)",
                          ["inventory/store.py"], [], "")
    item2.update(status="running", attempts=1, steps=3)
    state = {"id": jid, "task": "新增 restock_below", "workspace": ws, "status": "running", "source": "selftest",
             "created": "2026-10-07 10:00:00", "updated": "2026-10-07 10:05:00", "models": {"planner": "fake", "worker": "fake"},
             "items": [item1, item2], "approved_at": "2026-10-07 10:01:00", "final_verify": "python3 -m pytest -q",
             "cancel_requested": False, "pause_requested": False, "model_calls": 9}
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    o2 = CodingOrchestrator(agent)   # 模擬重新啟動：讀回既有的 job
    job = o2.get(jid)
    assert job["status"] == "failed" and job["interrupted"], job["status"]
    o2.resume(jid)
    wait(job, {"done", "partial", "failed"})
    assert job["status"] == "done", (job["status"], job.get("error"))
    assert job["items"][0]["steps"] == 5 and job["items"][0]["status"] == "done", "已完成的項目不應該重做"
    assert "def restock_below" in open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read()
    o2.stop_service()


def t_main_session_blocks_edit(agent, orch, ws, ollama):
    out = agent.run_tool({"action": {"command": "scripts/code_write_cmd.py", "args": "x.py"}})
    assert out.startswith("[ERROR] 主對話不直接修改程式碼"), out
    guard = agent.guard_check({"action": {"command": "scripts/code_job_cancel_cmd.py", "args": "latest"}})
    assert guard and guard["skill"] == "code_job_cancel", guard


def t_skill_scripts(agent, orch, ws, ollama):
    """程式技能腳本本身的保證：SEARCH/REPLACE 的寬鬆比對、省略／縮水／改壞語法的拒絕、路徑邊界、備份、指令安全檢查、真的 pytest。"""
    import subprocess
    scripts = os.path.join(agent.script_dir, "skills_system", "scripts")
    bdir = tempfile.mkdtemp(prefix="selftest_backup_")
    env = dict(os.environ, CODE_WORKSPACE=ws, CODE_BACKUP_DIR=bdir)

    def run(script, args, payload=None):
        if payload is not None:
            pf = os.path.join(bdir, "payload.txt")
            with open(pf, "w", encoding="utf-8") as f:
                f.write(payload)
            args = args + ["--payload", pf]
        r = subprocess.run([sys.executable, os.path.join(scripts, script)] + args, cwd=ws, env=env, capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL)
        return (r.stdout + r.stderr).strip()

    store = os.path.join(ws, "inventory", "store.py")
    orig = open(store, encoding="utf-8").read()
    # 行號被抄進 SEARCH、縮排錯位 → 仍然對得到
    out = run("code_edit_cmd.py", ["inventory/store.py"], "<<<<<<< SEARCH\n  27| def total_value(self):\n  28|     return sum(i.value() for i in self.items.values())\n"
              "=======\ndef total_value(self):\n    return round(sum(i.value() for i in self.items.values()), 2)\n>>>>>>> REPLACE\n")
    assert out.startswith("[PASS]") and "        return round(" in open(store, encoding="utf-8").read(), out
    # 「其餘不變」的省略、整份縮水、改壞語法 → 不寫入
    before = open(store, encoding="utf-8").read()
    assert run("code_edit_cmd.py", ["inventory/store.py", "--whole"], "```python\nclass Inventory:\n    # ... rest of the code unchanged ...\n```").startswith("[ERROR]")
    assert run("code_edit_cmd.py", ["inventory/store.py"], "<<<<<<< SEARCH\n    def report(self):\n=======\n    def report(self)\n>>>>>>> REPLACE\n").startswith("[ERROR]")
    assert open(store, encoding="utf-8").read() == before, "被拒絕的修改不應該寫入"
    # 路徑邊界、.git、已存在的檔案
    assert run("code_write_cmd.py", ["../outside.py"], "x = 1").startswith("[ERROR]")
    assert run("code_write_cmd.py", [".git/config"], "x").startswith("[ERROR]")
    assert run("code_write_cmd.py", ["inventory/store.py"], "x = 1").startswith("[ERROR]")
    # 備份記下原本的內容
    manifest = json.load(open(os.path.join(bdir, "manifest.json"), encoding="utf-8"))
    assert manifest["inventory/store.py"]["existed"] and open(os.path.join(bdir, "files", "inventory", "store.py"), encoding="utf-8").read() == orig
    # 指令安全檢查（引號裡的分隔符號不算）
    for bad in ("rm -rf build", "git push origin main", "pip install requests", "cat x > /etc/passwd", "curl http://x", "ls $(pwd)"):
        assert run("code_run_cmd.py", [bad]).startswith("[ERROR] 不允許"), bad
    assert run("code_run_cmd.py", ["python3 -c 'import time; time.sleep(0.1); print(\"ok; done\")'"]).startswith("[PASS]")
    # 模型沒有把整個指令包在一組引號裡（harness 拆成好幾個參數）：引號裡的 ; ( ) 要保留（以前接回去引號就不見了）
    out = run("code_run_cmd.py", ["python3", "-c", "print('a; b (c)')"])
    assert out.startswith("[PASS]") and "a; b (c)" in out, out
    assert run("code_run_cmd.py", ["ls", "tests/*.py"]).startswith("[PASS]"), "萬用字元要保持原樣"
    out = run("host_runcmd_cmd.py", ["python3", "-c", "print('x; y')"])
    assert out.startswith("[PASS]") and "x; y" in out, out
    assert run("code_run_cmd.py", ["make install"]).startswith("[ERROR] 不允許")
    # 會污染其他測試的測試檔（模組層級替換 sys.modules、改掉專案類別的屬性）→ code_check 報錯；測試函式裡的 monkeypatch 不算
    with open(os.path.join(ws, "tests", "test_selftest_mock.py"), "w", encoding="utf-8") as f:
        f.write("import sys\nfrom unittest.mock import MagicMock\nfrom inventory.store import Inventory\n"
                "sys.modules['inventory.storage'] = MagicMock()\nInventory.total_value = lambda self: 0\n\n"
                "def test_ok(monkeypatch):\n    monkeypatch.setattr(Inventory, 'report', lambda self: '')\n")
    out = run("code_check_cmd.py", ["tests/test_selftest_mock.py"])
    assert out.startswith("[ERROR]") and "sys.modules['inventory.storage']" in out and "Inventory.total_value" in out \
        and out.count("模組層級替換") == 2, out
    os.remove(os.path.join(ws, "tests", "test_selftest_mock.py"))
    # 真的 pytest：assert 失敗時看得到實際值；通過／失敗數在第一行；第一行一定是 [PASS]／[ERROR]
    with open(os.path.join(ws, "tests", "test_selftest_fail.py"), "w", encoding="utf-8") as f:
        f.write("def test_x():\n    v = 4\n    assert v == 5\n")
    out = run("code_test_cmd.py", ["tests/test_selftest_fail.py"])
    assert out.startswith("[ERROR] 測試失敗：pytest") and "1 failed" in out.split("\n", 1)[0] and "assert 4 == 5" in out, out
    out = run("code_run_cmd.py", ["python3 -m pytest -q tests/test_selftest_fail.py"])
    assert out.startswith("[ERROR] 指令失敗") and "1 failed" in out.split("\n", 1)[0], out
    out = run("code_test_cmd.py", ["tests/test_store.py"])
    assert out.startswith("[PASS] 測試全部通過：pytest") and " passed" in out.split("\n", 1)[0], out
    # .gitignore 排除的目錄（建置產物、下載來的）不掃描；! 例外照 git 的規則；從子目錄掃描時上層的 .gitignore 也算；明確指定時照樣掃
    made = {"cmake-build-debug/gen.py": "ZZ_IGNORED = 1\n", "out_keep/keep.py": "ZZ_KEPT = 1\n", "out1/x.py": "ZZ_OUT = 1\n",
            "inventory/cache/tmp/c.py": "ZZ_DEEP = 1\n", ".gitignore": "# 建置產物\ncmake-build-*/\nout*/\n!out_keep/\n**/cache/tmp\n"}
    for rel, text in made.items():
        os.makedirs(os.path.dirname(os.path.join(ws, rel)) or ws, exist_ok=True)
        with open(os.path.join(ws, rel), "w", encoding="utf-8") as f:
            f.write(text)
    out = run("code_search_cmd.py", ["ZZ_"])
    assert "out_keep/keep.py" in out and "cmake-build-debug" not in out and "out1/" not in out and "cache/tmp" not in out, out
    out = run("code_search_cmd.py", ["ZZ_", "inventory"])
    assert "cache/tmp" not in out, out
    assert "gen.py" in run("code_search_cmd.py", ["ZZ_", "cmake-build-debug"])
    for d in ("cmake-build-debug", "out_keep", "out1", "inventory/cache"):
        shutil.rmtree(os.path.join(ws, d), ignore_errors=True)
    os.remove(os.path.join(ws, ".gitignore"))
    shutil.rmtree(bdir, ignore_errors=True)


def t_cpp_scripts(agent, orch, ws, ollama):
    """C／C++：真的 gtest（CMake＋ctest、make test、沒有建置檔時直接用 g++）、失敗與編譯錯誤的整理、code_check 用編譯器、
    改到括號不成對（輸出被截斷）的修改不寫入、C++ 的結構大綱與名稱索引。需要 g++、gtest（~/.local 或系統）與 cmake。"""
    import subprocess
    scripts = os.path.join(agent.script_dir, "skills_system", "scripts")
    base = tempfile.mkdtemp(prefix="selftest_cpp_")

    def copy(name, as_name=None):
        dst = os.path.join(base, as_name or name)
        shutil.copytree(os.path.join(HERE, "coding_fixtures", name), dst)
        return dst

    def run(cwd, script, args, payload=None):
        env = dict(os.environ, CODE_WORKSPACE=cwd, CODE_BACKUP_DIR=os.path.join(base, "backup_" + os.path.basename(cwd)))
        if payload is not None:
            pf = os.path.join(base, "payload.txt")
            with open(pf, "w", encoding="utf-8") as f:
                f.write(payload)
            args = args + ["--payload", pf]
        r = subprocess.run([sys.executable, os.path.join(scripts, script)] + args, cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=300, stdin=subprocess.DEVNULL)
        return (r.stdout + r.stderr).strip()

    try:
        geo, rb = copy("geometry_cpp"), copy("ringbuf_c")
        out = run(geo, "code_test_cmd.py", [])
        assert out.startswith("[PASS]") and "gtest（CMake＋ctest） 7 passed" in out, out
        out = run(rb, "code_test_cmd.py", [])
        assert out.startswith("[PASS]") and "make test" in out and "4 passed" in out, out
        # 斷言失敗：失敗的測試、期望值與實際值、相對路徑
        with open(os.path.join(geo, "tests", "test_shapes.cpp"), "a", encoding="utf-8") as f:
            f.write("\nTEST(CircleTest, Wrong) { EXPECT_DOUBLE_EQ(Circle(1.0).area(), 3.0); }\n")
        out = run(geo, "code_test_cmd.py", ["tests/test_shapes.cpp"])
        assert out.startswith("[ERROR] 測試失敗") and "1 failed、4 passed" in out and "✗ CircleTest.Wrong" in out \
            and "tests/test_shapes.cpp:" in out and base not in out, out
        # 編譯錯誤：檔案:行號: error 與那一行原始碼
        direct = copy("geometry_cpp", "geometry_direct")
        os.remove(os.path.join(direct, "CMakeLists.txt"))
        out = run(direct, "code_test_cmd.py", [])
        assert out.startswith("[PASS]") and "直接編譯" in out and "7 passed" in out, out
        src = os.path.join(direct, "src", "circle.cpp")
        text = open(src, encoding="utf-8").read()
        with open(src, "w", encoding="utf-8") as f:
            f.write(text.replace("M_PI * radius_ * radius_", "M_PI * radius_ * radiuss_"))
        out = run(direct, "code_test_cmd.py", [])
        assert out.startswith("[ERROR] 測試失敗") and "編譯失敗（1 個錯誤）" in out and "src/circle.cpp:16:" in out \
            and "radiuss_" in out, out
        out = run(direct, "code_check_cmd.py", ["src/circle.cpp"])
        assert out.startswith("[ERROR]") and "src/circle.cpp:16:" in out and "was not declared" in out, out
        # code_edit：改完括號不成對（輸出被截斷）→ 不寫入；正常的 C++ 修改 → 寫入
        before = open(src, encoding="utf-8").read()
        out = run(direct, "code_edit_cmd.py", ["src/circle.cpp"],
                  "<<<<<<< SEARCH\ndouble Circle::area() const { return M_PI * radius_ * radiuss_; }\n=======\n"
                  "double Circle::area() const {\n    return M_PI * radius_ * radius_;\n\n>>>>>>> REPLACE\n")
        assert out.startswith("[ERROR]") and "沒有對應的「}」" in out and open(src, encoding="utf-8").read() == before, out
        out = run(direct, "code_edit_cmd.py", ["src/circle.cpp"],
                  "<<<<<<< SEARCH\ndouble Circle::area() const { return M_PI * radius_ * radiuss_; }\n=======\n"
                  "double Circle::area() const { return M_PI * radius_ * radius_; }\n>>>>>>> REPLACE\n")
        assert out.startswith("[PASS]") and "括號配對 OK" in out, out
        assert run(direct, "code_check_cmd.py", ["src/circle.cpp"]).startswith("[PASS]")
        # repo_map：C++ 的大綱、建置系統、建議的測試指令；code_refs：定義、宣告、使用
        out = run(geo, "repo_map_cmd.py", ["."])
        assert "建議的測試指令：code_test" in out and "CMake（有註冊測試" in out and "double Circle::area() const L16" in out, out
        out = run(geo, "code_refs_cmd.py", ["total_area"])
        assert "定義 1 處、宣告 1 處" in out and "src/registry.cpp L48" in out, out
        job = {"workspace": geo}
        idx = orch.symbol_index(job)
        assert idx["Circle"][0][0] == "include/geometry/circle.hpp" and idx["Circle.area"][0][0] == "src/circle.cpp", idx.get("Circle.area")
        assert orch._clean_verify("scripts/code_test_cmd.py tests/test_shapes.cpp")[0] == "code_test tests/test_shapes.cpp"
        # 災難性回溯的回歸測試（2026-10-09 SWE-bench 評測找到）：一長串大寫的巨集名稱後面接對不上的字，舊的 _POST_RE 要指數時間——
        # fmt 內附的 gmock.h、redis 的 jemalloc 標頭讓 repo_map 卡 10 分鐘、規劃時的符號索引卡到 job 逾時。在子程序裡跑、限時 10 秒。
        import multiprocessing
        hdr = ("#if defined(_MSC_VER) && _MSC_VER >= 1915\n#define GMOCK_MAYBE_5046_ 5046\n#endif\n"
               "GTEST_DISABLE_MSC_WARNINGS_PUSH_(4251 GMOCK_MAYBE_5046_ /* x */)\nnamespace testing {\nint f(int a);\n}\n")
        proc = multiprocessing.Process(target=_outline_probe, args=(scripts, hdr, "GTEST_DISABLE_MSC_WARNINGS_PUSH_GMOCK_MAYBE_5046_ namespace"))
        proc.start()
        proc.join(10)
        hung = proc.is_alive()
        if hung:
            proc.terminate()
            proc.join()
        assert not hung and proc.exitcode == 0, "C++ 大綱的簽名後綴比對又出現災難性回溯（_cpp_common._POST_RE）"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _outline_probe(scripts, hdr, post):
    sys.path.insert(0, scripts)
    import _cpp_common as cp_mod
    assert cp_mod._POST_RE.fullmatch(post) is None
    assert any("f" in str(e) for e in cp_mod.outline(hdr)), cp_mod.outline(hdr)


def t_listed_files(agent, orch, ws, ollama):
    """任務「一行一個」列出要建立的檔案時：計畫漏掉的檔案依清單順序補上；worker 不能新建清單以外的原始檔（測試檔可以）。"""
    from agent_core.coding_worker import CodingWorker
    task = "依照規格實作：\n1. geo/shape.hpp\n2. geo/shape.cpp\n3. geo/main.cpp\n4. makefile\n（例如套件的 __init__.py 也要）"
    job = {"id": 999, "workspace": ws, "task": task, "items": []}
    assert orch.listed_new_files(job) == ["geo/shape.hpp", "geo/shape.cpp", "geo/main.cpp", "makefile"], orch.listed_new_files(job)
    items = [orch.new_item(1, "shape", "做 shape", ["geo/shape.hpp", "geo/shape.cpp"], [], "")]
    warns = []
    items = orch.cover_listed_files(job, items, warns)
    assert [it["files"] for it in items] == [["geo/shape.hpp", "geo/shape.cpp"], ["geo/main.cpp"], ["makefile"]], items
    assert warns and "geo/main.cpp" in warns[0], warns
    job["items"] = items
    w = CodingWorker(orch, job, items[0], 1)
    _, _, mode, err = w._payload_mode("code_write_cmd.py", ["geo/circle.cpp"])
    assert err and "不能新建" in err and "geo/shape.hpp" in err, err
    _, _, mode, err = w._payload_mode("code_write_cmd.py", ["geo/shape.cpp"])
    assert err is None and mode == "write", (mode, err)
    _, _, mode, err = w._payload_mode("code_write_cmd.py", ["tests/test_shape.cpp"])
    assert err is None and mode == "write", (mode, err)
    job2 = {"id": 998, "workspace": ws, "task": "在 Inventory 新增 restock_below，並更新 tests/test_store.py", "items": []}
    assert orch.listed_new_files(job2) == [] and orch.cover_listed_files(job2, list(items[:1]), []) == items[:1]
    job3 = {"id": 997, "workspace": ws, "task": "CLI 新增 export：python3 -m inventory.cli --file inv.json export out.csv", "items": []}
    got, _ = orch.normalize_items(job3, [{"title": "匯出", "goal": "新增 inventory/export.py", "files": ["inventory/export.py"],
                                          "context_files": [], "verify": ""}])
    assert got and got[0]["files"] == ["inventory/export.py"], "例句裡的 inv.json、out.csv 不是要建立的檔案，不能觸發限制"
    got, w = orch.normalize_items(job, [{"title": "別的", "goal": "做 x", "files": ["other/x.cpp"], "context_files": [], "verify": ""}])
    assert got and got[0]["files"] == ["other/x.cpp"] and any("這次不限制" in x for x in w), (got, w)


def t_fix_must_not_regress(agent, orch, ws, ollama):
    """整體驗證失敗 → 修正 worker 把程式改壞（通過的測試變少）→ 還原到修正前，報告的是修正前的結果。"""
    failing_test = lambda t: "```python\n" + current_file(t).rstrip("\n") + "\n\n\ndef test_wrong(inv):\n    assert inv.restock_below(2, 3) == ['nope']\n```"
    breaking = lambda t: "```python\n" + current_file(t).rstrip("\n") + "\n\nraise RuntimeError('broken by fix')\n```"
    script = [edit("scripts/code_edit_cmd.py", "inventory/store.py"), edit("code_edit", "tests/test_store.py"), DONE]
    for _ in range(2):   # 修正 worker 兩次嘗試：都把 store.py 改壞
        script += [edit("scripts/code_edit_cmd.py", "inventory/store.py"), DONE, DONE, DONE]
    good = lambda t: "```python\n" + current_file(t).rstrip("\n") + "\n" + GOOD_STORE_ADDITION + "```"
    ollama.chat = FakeModel(script, [good, failing_test] + [breaking] * 6)
    job, _ = orch.submit("在 Inventory 新增 restock_below，並加測試", ws, "selftest")
    wait(job, {"awaiting_approval"})
    orch.edit_item(job["id"], 1, {"verify": ""})
    orch.set_final_verify(job["id"], "python3 -m pytest -q")
    orch.approve(job["id"])
    wait(job, {"done", "partial", "failed"}, timeout=180)
    text = open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read()
    assert "def restock_below" in text and "broken by fix" not in text, "修正把程式改壞了，應該還原到修正前"
    assert job["final_ok"] is False and "1 failed" in job["final_output"].split("\n", 1)[0], job["final_output"][:300]
    assert any("已把" in e["text"] and "還原到修正前" in e["text"] for e in orch.events(job["id"])), "應該有還原的事件"


_ROS_PKG = {
    "src/my_pkg/package.xml": "<?xml version=\"1.0\"?>\n<package format=\"3\">\n  <name>my_pkg</name>\n"
                              "  <buildtool_depend>ament_cmake</buildtool_depend>\n  <depend>rclcpp</depend>\n  <depend>std_msgs</depend>\n"
                              "  <test_depend>ament_cmake_gtest</test_depend>\n  <export><build_type>ament_cmake</build_type></export>\n</package>\n",
    "src/my_pkg/CMakeLists.txt": "cmake_minimum_required(VERSION 3.8)\nproject(my_pkg)\nset(CMAKE_CXX_STANDARD 17)\n"
                                 "find_package(ament_cmake REQUIRED)\nfind_package(rclcpp REQUIRED)\nfind_package(std_msgs REQUIRED)\n"
                                 "include_directories(include)\nadd_executable(talker src/talker.cpp src/filter.cpp)\n"
                                 "ament_target_dependencies(talker rclcpp std_msgs)\nif(BUILD_TESTING)\n  find_package(ament_cmake_gtest REQUIRED)\n"
                                 "  ament_add_gtest(test_filter test/test_filter.cpp src/filter.cpp)\nendif()\nament_package()\n",
    "src/my_pkg/include/my_pkg/filter.hpp": "#pragma once\n#include <cstddef>\n#include <vector>\nnamespace my_pkg {\n"
                                            "double moving_average(const std::vector<double>& xs, std::size_t window);\n}\n",
    "src/my_pkg/src/filter.cpp": "#include <ctime>\n#include \"my_pkg/filter.hpp\"\nnamespace my_pkg {\n"
                                 "double moving_average(const std::vector<double>& xs, std::size_t window) {\n"
                                 "  if (xs.empty() || window == 0) return 0.0;\n  std::size_t n = xs.size() < window ? xs.size() : window;\n"
                                 "  double s = 0.0;\n  for (std::size_t i = xs.size() - n; i < xs.size(); ++i) s += xs[i];\n  return s / n;\n}\n}\n",
    "src/my_pkg/src/talker.cpp": "#include <memory>\n#include \"rclcpp/rclcpp.hpp\"\n#include \"std_msgs/msg/string.hpp\"\n"
                                 "#include \"my_pkg/filter.hpp\"\nint main(int argc, char** argv) {\n  rclcpp::init(argc, argv);\n"
                                 "  rclcpp::spin(std::make_shared<rclcpp::Node>(\"talker\"));\n  rclcpp::shutdown();\n  return 0;\n}\n",
    "src/my_pkg/test/test_filter.cpp": "#include <gtest/gtest.h>\n#include \"my_pkg/filter.hpp\"\n"
                                       "TEST(Filter, Average) { EXPECT_DOUBLE_EQ(my_pkg::moving_average({1, 2, 3, 4}, 2), 3.5); }\n"
                                       "TEST(Filter, Empty) { EXPECT_DOUBLE_EQ(my_pkg::moving_average({}, 3), 0.0); }\n",
    "src/my_pkg/test/test_talker_node.cpp": "#include <gtest/gtest.h>\n#include \"rclcpp/rclcpp.hpp\"\n"
                                            "TEST(Talker, Init) { rclcpp::init(0, nullptr); SUCCEED(); }\n",
    # 套件自己定義的介面：建置時才產生 my_pkg/msg/status.hpp
    "src/my_pkg/msg/Status.msg": "string text\n",
    "src/my_pkg/src/status_user.cpp": "#include \"my_pkg/msg/status.hpp\"\n#include \"my_pkg/filter.hpp\"\n"
                                      "int status_size() { return 1; }\n",
    # 第三方程式附了跟系統標頭同名的 time.h（fmt 就是這樣）：那個目錄用 -I 的話，<ctime> 會找到它
    "src/my_pkg/third_party/fmtlite/time.h": "#error \"shadowed the system time.h\"\n",
    "src/my_pkg/third_party/fmtlite/fmtlite.h": "#pragma once\ninline int fmtlite_version() { return 1; }\n",
    # 命名空間在標頭打開、在 .cpp 關閉（rf2o 就是這樣）：單一檔案的括號不成對，合起來編譯得過
    "src/my_pkg/include/my_pkg/ns_open.hpp": "#pragma once\nnamespace my_pkg {\nint ns_value();\n",
    "src/my_pkg/src/ns_close.cpp": "#include \"my_pkg/ns_open.hpp\"\nint ns_value() { return 1; }\n}  // namespace my_pkg\n",
}
_ROS_LINTER_TEST = ("from ament_flake8.main import main_with_errors\nimport pytest\n\n\n@pytest.mark.flake8\n@pytest.mark.linter\n"
                    "def test_flake8():\n    rc, errors = main_with_errors(argv=[])\n    assert rc == 0, '\\n'.join(errors)\n")
for _p in ("amr_tools", "amr_nav_py"):          # ament_python 套件：範本的 linter 測試（需要 ament_flake8，這台主機沒有）
    _ROS_PKG.update({
        f"src/{_p}/package.xml": f"<?xml version=\"1.0\"?>\n<package format=\"3\">\n  <name>{_p}</name>\n  <depend>rclpy</depend>\n"
                                 "  <test_depend>ament_flake8</test_depend>\n  <export><build_type>ament_python</build_type></export>\n</package>\n",
        f"src/{_p}/setup.py": f"from setuptools import setup\nsetup(name='{_p}', packages=['{_p}'])\n",
        f"src/{_p}/{_p}/__init__.py": f'"""{_p}"""\n',
        f"src/{_p}/test/test_flake8.py": _ROS_LINTER_TEST})
_ROS_PKG.update({
    "src/amr_tools/amr_tools/battery.py": "def percent(voltage, empty=22.0, full=25.2):\n"
                                          "    return max(0.0, min(100.0, (voltage - empty) / (full - empty) * 100.0))\n",
    "src/amr_tools/amr_tools/node.py": "import rclpy\nfrom rclpy.node import Node\n",
    "src/amr_tools/test/test_battery.py": "from amr_tools.battery import percent\n\n\ndef test_mid():\n"
                                          "    assert abs(percent(23.6) - 50.0) < 1e-6\n\n\ndef test_clamp():\n"
                                          "    assert percent(30) == 100.0 and percent(10) == 0.0\n",
    "src/amr_tools/test/test_node.py": "from amr_tools import node\n\n\ndef test_node():\n    assert node.Node\n",
})


def _write_tree(base, files):
    for rel, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(base, rel)), exist_ok=True)
        with open(os.path.join(base, rel), "w", encoding="utf-8") as f:
            f.write(text)


def t_ros2_workspace(agent, orch, ws, ollama):
    """ROS 2 的 colcon 工作區、這台主機沒有 ROS 2（使用者的機器就是這樣：ROS 2 在容器裡）：#include "my_pkg/x.hpp" 對到套件自己的
    include 目錄；缺宣告過的外部依賴（rclcpp）不算程式的錯、講清楚原因；專案自己的 #include 寫錯、真的編譯錯誤照樣抓到；
    code_test 只編譯那個套件、純 C++ 的 gtest 照跑、依賴 ROS 的跳過；整體驗證不用 CMake 建置 ROS 套件。"""
    import subprocess
    scripts = os.path.join(agent.script_dir, "skills_system", "scripts")
    rws = tempfile.mkdtemp(prefix="selftest_rosws_")
    _write_tree(rws, _ROS_PKG)
    env = dict(os.environ, CODE_WORKSPACE=rws)
    env.pop("AMENT_PREFIX_PATH", None)

    def run(script, args):
        r = subprocess.run([sys.executable, os.path.join(scripts, script)] + args, cwd=rws, env=env, capture_output=True,
                           text=True, timeout=300, stdin=subprocess.DEVNULL)
        return (r.stdout + r.stderr).strip()

    talker = os.path.join(rws, "src/my_pkg/src/talker.cpp")
    filt = os.path.join(rws, "src/my_pkg/src/filter.cpp")
    try:
        out = run("code_check_cmd.py", ["src/my_pkg/src/filter.cpp", "src/my_pkg/src/talker.cpp"])
        assert out.startswith("[PASS]") and "1 個缺外部依賴" in out and "rclcpp/rclcpp.hpp" in out and "不是程式的錯誤" in out \
            and "colcon build --packages-select my_pkg" in out and "my_pkg/filter.hpp" not in out, out
        # 改標頭：用到它的原始檔都會編譯（含測試），照樣分得出外部依賴
        out = run("code_check_cmd.py", ["src/my_pkg/include/my_pkg/filter.hpp"])
        assert out.startswith("[PASS]") and "編譯器檢查了 3 個檔案" in out, out   # 一個標頭最多編譯 3 個使用者
        # 套件自己定義的介面（msg/Status.msg）→ 建置時才產生，不算錯；沒有定義的介面照樣是錯誤
        out = run("code_check_cmd.py", ["src/my_pkg/src/status_user.cpp"])
        assert out.startswith("[PASS]") and "建置時才產生的標頭 my_pkg/msg/status.hpp" in out, out
        user = os.path.join(rws, "src/my_pkg/src/status_user.cpp")
        with open(user, "a", encoding="utf-8") as f:
            f.write('#include "my_pkg/msg/nope.hpp"\n')
        out = run("code_check_cmd.py", ["src/my_pkg/src/status_user.cpp"])
        assert out.startswith("[ERROR]") and "my_pkg/msg/nope.hpp" in out, out
        with open(user, "w", encoding="utf-8") as f:
            f.write(_ROS_PKG["src/my_pkg/src/status_user.cpp"])
        # 命名空間跨檔案打開／關閉：主對話照實列出；coding job 裡這兩個檔案沒被改過（或改之前就這樣）→ 只提醒、照常編譯
        pair = ["src/my_pkg/include/my_pkg/ns_open.hpp", "src/my_pkg/src/ns_close.cpp"]
        out = run("code_check_cmd.py", pair)
        assert out.startswith("[ERROR]") and out.count("語法錯誤") == 2, out
        env["CODE_BACKUP_DIR"] = tempfile.mkdtemp(prefix="selftest_bak_", dir=rws)
        out = run("code_check_cmd.py", pair)
        del env["CODE_BACKUP_DIR"]
        assert out.startswith("[PASS]") and out.count("job 開始前就是這樣") == 2 and "編譯器檢查了 1 個檔案" in out, out
        # 編譯器在 rclcpp 就停了，後面專案自己的 #include 寫錯也要抓到；真正的編譯錯誤照樣報
        with open(talker, "a", encoding="utf-8") as f:
            f.write('#include "my_pkg/filtr.hpp"\n')
        orig = open(filt, encoding="utf-8").read()
        with open(filt, "w", encoding="utf-8") as f:
            f.write(orig.replace("return s / n;", "return s / count;"))
        out = run("code_check_cmd.py", ["src/my_pkg/src/filter.cpp", "src/my_pkg/src/talker.cpp"])
        assert out.startswith("[ERROR]") and "my_pkg/filtr.hpp" in out and "count" in out and "was not declared" in out, out
        with open(filt, "w", encoding="utf-8") as f:
            f.write(orig)
        with open(talker, encoding="utf-8") as f:
            text = f.read()
        with open(talker, "w", encoding="utf-8") as f:
            f.write(text.replace('#include "my_pkg/filtr.hpp"\n', ""))
        # code_test：整個工作區 → 每個套件分開跑：C++ 只編譯 my_pkg、純 C++ 的 gtest 跑、依賴 ROS 的跳過並說明；Python 在套件目錄
        # 跑 pytest（import 得到 amr_tools），缺 ament_flake8／rclpy 的測試檔跳過；整個套件都跑不了的另外列出，不算失敗
        out = run("code_test_cmd.py", [])
        first = out.split("\n", 1)[0]
        assert first.startswith("[PASS]") and "src/my_pkg 2 passed（跳過 1 個缺外部依賴的測試檔）" in first \
            and "src/amr_tools 2 passed（跳過 2 個缺外部依賴的測試檔）" in first and "另外 1 組缺外部依賴" in first \
            and "colcon test --packages-select my_pkg" in out and "src/amr_tools/test/test_node.py：import rclpy" in out, out
        out = run("code_test_cmd.py", ["src/amr_nav_py"])
        assert out.startswith("[ERROR] 沒辦法在這台主機跑這些測試（缺外部依賴，不是程式的錯誤）"), out
        bat = os.path.join(rws, "src/amr_tools/test/test_battery.py")
        with open(bat, encoding="utf-8") as f:
            text = f.read()
        with open(bat, "w", encoding="utf-8") as f:
            f.write(text.replace("- 50.0)", "- 49.0)"))
        out = run("code_test_cmd.py", ["src/amr_tools"])
        assert out.startswith("[ERROR] 測試失敗") and "1 failed" in out and "src/amr_tools/test/test_battery.py:5" in out, out
        with open(bat, "w", encoding="utf-8") as f:
            f.write(text)
        out = run("code_test_cmd.py", ["src/my_pkg/test/test_talker_node.cpp"])
        assert out.startswith("[ERROR] 沒辦法在這台主機跑這些測試（缺外部依賴，不是程式的錯誤）"), out
        with open(os.path.join(rws, "src/my_pkg/test/test_filter.cpp"), encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(rws, "src/my_pkg/test/test_filter.cpp"), "w", encoding="utf-8") as f:
            f.write(text.replace("3.5);", "3.0);"))
        out = run("code_test_cmd.py", ["src/my_pkg"])
        assert out.startswith("[ERROR] 測試失敗") and "1 failed" in out and "src/my_pkg/test/test_filter.cpp:3" in out, out
        # 整體驗證：沒有 ROS 2 時不用 CMake 建置 ROS 套件（find_package(ament_cmake) 一定失敗，不是程式的問題）
        from agent_core import coding_job
        saved = os.environ.pop("AMENT_PREFIX_PATH", None)
        try:
            assert coding_job.cpp.build_command(os.path.join(rws, "src/my_pkg")) is None
        finally:
            if saved is not None:
                os.environ["AMENT_PREFIX_PATH"] = saved
    finally:
        shutil.rmtree(rws, ignore_errors=True)


def t_ros2_job_env_tests(agent, orch, ws, ollama):
    """coding job 的驗證指令在這台主機跑不了（測試全部需要 ROS 2）：那一項以靜態檢查為準、不算失敗，整體驗證改用靜態檢查，
    job 照樣完成——不會派 worker 去「修」本來就沒錯的程式。"""
    rws = tempfile.mkdtemp(prefix="selftest_rosjob_")
    _write_tree(rws, _ROS_PKG)
    target = "src/amr_nav_py/amr_nav_py/__init__.py"

    class RosFake(FakeModel):
        def __call__(self, model=None, messages=None, format=None, **kw):
            props = sorted((format or {}).get("properties", {})) if isinstance(format, dict) else []
            if "files_to_read" in props:
                data = {"understanding": "加版本常數", "files_to_read": [target], "questions": []}
            elif "items" in props:
                data = {"summary": "加版本常數", "final_verify": "code_test src/amr_nav_py", "risks": [],
                        "items": [{"title": "加 VERSION", "goal": "在 amr_nav_py/__init__.py 加上 VERSION = '1.0'", "files": [target],
                                   "context_files": [], "verify": "code_test src/amr_nav_py"}]}
            else:
                return super().__call__(model, messages, format, **kw)
            self.calls.append(props)
            return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 100, "eval_count": 20}

    saved = os.environ.pop("AMENT_PREFIX_PATH", None)
    try:
        ollama.chat = RosFake([edit("scripts/code_write_cmd.py", "amr_nav_py/__init__.py"), edit("scripts/code_edit_cmd.py", target), DONE],
                              [lambda t: "```python\n" + current_file(t).rstrip("\n") + "\nVERSION = '1.0'\n```"])
        job, err = orch.submit(f"在 {target} 加上 VERSION = '1.0'", rws, "selftest")
        assert not err, err
        wait(job, {"awaiting_approval", "failed"})
        assert f"在 {target} 加上" in job["items"][0]["goal"], job["items"][0]["goal"]
        orch.approve(job["id"])
        wait(job, {"done", "partial", "failed", "needs_attention"}, timeout=180)
        it = job["items"][0]
        assert not os.path.exists(os.path.join(rws, "amr_nav_py")), "用套件裡的相對路徑建檔應該被擋下"
        assert any("專案裡已經有 src/amr_nav_py/amr_nav_py/__init__.py" in (e.get("text") or "") for e in orch.events(job["id"])), \
            [e.get("text", "")[:120] for e in orch.events(job["id"]) if e["type"] == "tool"]
        assert job["status"] == "done" and it["status"] == "done" and it["attempts"] == 1, \
            (job["status"], [(i["status"], i["attempts"], i["summary"]) for i in job["items"]], job.get("final_output", "")[:500])
        assert "VERSION = '1.0'" in open(os.path.join(rws, target), encoding="utf-8").read()
        assert job["final_ok"] is True and "外部依賴，改用靜態檢查" in job["final_output"], job["final_output"][:800]
    finally:
        if saved is not None:
            os.environ["AMENT_PREFIX_PATH"] = saved
        shutil.rmtree(rws, ignore_errors=True)


def t_brownfield_v42(agent, orch, ws, ollama):
    """既有專案（v4.2，SWE-bench 評測找到的問題）：django 型專案的測試指令、建議指令的佔位符不能照抄、沒有 pytest 算環境問題、
    大型專案的整體驗證改跑每一項的驗證指令、大型檔案的修改視窗以目標為中心、寫入後附上檔案的結構、空轉時明說已經有哪些。"""
    import subprocess
    from agent_core import coding_worker as cw
    from agent_core.coding_job import _WHOLE_SUITE_RE
    scripts = os.path.join(agent.script_dir, "skills_system", "scripts")
    base = tempfile.mkdtemp(prefix="selftest_v42_")
    try:
        # (1) django 型專案：tests/runtests.py → 建議 runtests；佔位符不能照抄進驗證指令
        dj = os.path.join(base, "dj")
        _write_tree(dj, {"tests/runtests.py": "print('ok')\n", "tests/app/tests.py": "def test_a():\n    pass\n",
                         "proj/__init__.py": "", "proj/core.py": "def f():\n    return 1\n"})
        env = dict(os.environ, CODE_WORKSPACE=dj)
        out = subprocess.run([sys.executable, os.path.join(scripts, "repo_map_cmd.py"), "."], cwd=dj, env=env,
                             capture_output=True, text=True).stdout
        assert "建議的測試指令：python3 tests/runtests.py <測試模組>" in out, out[:400]
        cmd, why = orch._clean_verify("python3 tests/runtests.py <測試模組>")
        assert cmd == "" and "佔位符" in (why or ""), (cmd, why)
        assert orch._clean_verify("python3 tests/runtests.py app.tests")[0] == "python3 tests/runtests.py app.tests"
        # (2) 這個 Python 沒有 pytest：環境問題（ENV_ONLY_HEAD），不是測試失敗
        env2 = dict(env, CODE_PYTHON="/usr/bin/python3")
        r = subprocess.run([sys.executable, os.path.join(scripts, "code_test_cmd.py"), "tests/app/tests.py"], cwd=dj, env=env2,
                           capture_output=True, text=True)
        head = (r.stdout or r.stderr).split("\n", 1)[0]
        has_pytest = subprocess.run(["/usr/bin/python3", "-c", "import pytest"], capture_output=True).returncode == 0
        assert has_pytest or head.startswith("[ERROR] 沒辦法在這台主機跑這些測試"), head
        # (3) 大型專案的整體驗證：「跑整套測試」改成依序跑每一項的驗證指令
        assert _WHOLE_SUITE_RE.match("python3 tests/runtests.py") and _WHOLE_SUITE_RE.match("code_test")
        assert not _WHOLE_SUITE_RE.match("python3 tests/runtests.py app.tests") and not _WHOLE_SUITE_RE.match("code_test tests/a.cpp")
        job = {"id": 901, "workspace": dj, "final_verify": "code_test", "test_files": 80,
               "items": [{"n": 1, "status": "done", "verify": "python3 -c \"print('item one ok')\""},
                         {"n": 2, "status": "done", "verify": "python3 -c \"print('item two ok')\""}]}
        out, ok = orch._final_check(job)
        assert ok and out.startswith("[PASS] 整體驗證通過（2 個驗證指令）") and "item two ok" in out, out[:300]
        job["items"][1]["verify"] = "python3 -c \"import sys; sys.exit(3)\""
        out, ok = orch._final_check(job)
        assert not ok and job["final_failing"] == [job["items"][1]["verify"]], (out[:300], job.get("final_failing"))
        job["test_files"] = 5          # 小專案照舊跑整體驗證指令
        orch._final_check(job)
        assert job["final_failing"] is None
        # (4) 修改視窗：目標在第 800 行之後也看得到
        content = "\n".join([f"x{i} = {i}" for i in range(1, 1201)] + ["def target_function(a):", "    return a"])
        ln = cw._focus_from_text(content, "修改 target_function 的回傳值")
        win = cw._edit_window(content.split("\n"), (ln, ln), 800)
        assert ln == 1201 and "def target_function" in win and win.startswith("…（前面還有"), (ln, win[:80])
        assert cw._edit_window(content.split("\n"), None, 800).startswith("x1 = 1")
        # (5) 寫入後附上檔案的結構；空轉時明說已經有哪些
        _write_tree(ws, {"pkg_v42/mod.py": "class Store:\n    def add(self, x):\n        return x\n\n\ndef helper(a):\n    return a\n"})
        job2 = {"id": 902, "workspace": ws, "items": [], "task": "t"}
        item = {"n": 1, "title": "t", "goal": "g", "files": ["pkg_v42/mod.py"], "context_files": [], "verify": ""}
        w = cw.CodingWorker(orch, job2, item, 1)
        out = w._after_tool("code_write_cmd.py", ["pkg_v42/mod.py"], "write", "PASS", "[PASS] 已建立 pkg_v42/mod.py")
        assert "現在有：class Store" in out and "def helper" in out, out
        out = w._after_tool("code_edit_cmd.py", ["pkg_v42/mod.py"], "blocks", "ERROR",
                            "[ERROR] pkg_v42/mod.py 沒有修改：新內容跟檔案目前的內容完全一樣")
        assert "目前已經有：" in out and "回報完成" in out, out
        w._after_tool("code_view_cmd.py", ["pkg_v42/mod.py"], None, "PASS", "[PASS] pkg_v42/mod.py（共 7 行，Python）第 2～3 行；")
        assert w.focus.get("pkg_v42/mod.py") == (2, 3), w.focus
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    results = []
    for name, fn in [("規劃修正、核准、用說的改、worker 修改、驗證、報告、還原", t_happy_path),
                     ("驗證失敗→交還 worker→換 worker 重試→停下來問→跳過", t_verify_fail_then_skip),
                     ("等核准時停止，不改任何檔案", t_cancel_while_waiting),
                     ("code_job_send／status／cancel 透過檔案與服務溝通", t_inbox_and_scripts),
                     ("程式重新啟動後，中斷的 job 從沒做完的項目接著做", t_resume_after_restart),
                     ("主對話不能直接改檔、停止 job 要確認", t_main_session_blocks_edit),
                     ("技能腳本：寬鬆比對、拒絕省略與改壞語法、路徑邊界、備份、指令安全檢查、真的 pytest、.gitignore", t_skill_scripts),
                     ("C／C++：gtest（CMake、make、直接編譯）、編譯錯誤、code_check、截斷的修改不寫入、大綱與名稱索引", t_cpp_scripts),
                     ("任務列出的檔案：計畫漏掉的補上、worker 不能新建清單以外的原始檔", t_listed_files),
                     ("整體驗證的修正把結果變差（通過的測試變少）→ 還原到修正前", t_fix_must_not_regress),
                     ("ROS 2 colcon 工作區（沒有 ROS 2）：套件的 include、外部依賴與產生的標頭不算錯、-iquote、跨檔的命名空間、純 C++ gtest 與套件的 pytest 照跑", t_ros2_workspace),
                     ("ROS 2：驗證的測試全部需要 ROS 2 → 以靜態檢查為準、套件裡的相對路徑補成完整路徑，job 照樣完成", t_ros2_job_env_tests),
                     ("既有專案（v4.2）：django 型的測試指令、佔位符、沒有 pytest 算環境問題、大型專案的整體驗證、修改視窗、寫入後的結構與空轉提示",
                      t_brownfield_v42)]:
        scenario(name, fn, results)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
