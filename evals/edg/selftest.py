"""低階執行器（agent_core/edg.py，新架構 D10 第 2 步）的離線自我測試：用寫好的圖、假的修正模型，不用真模型（幾秒）。

檢查圖、照收據守門（expect、complete）、從收據帶入參數（一項一個實例、去重、上限）、第 1 級（執行前的參數檢查、修一次、程式核對修正、
逾時只照規格的 narrow 縮小、env 不修）、依賴沒成功就跳過、判斷節點交回中階、確認關卡停下來與接回、存檔（job.json、收據、軌跡、#編號）、
修正的模型呼叫（prompt 只給規格、錯誤、子目標）。

    python3 evals/edg/selftest.py
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts"]


class Skip(Exception):
    pass


class FakeFixer:
    """照劇本回修正（None＝沒有回覆）；記下每一次收到的 req。"""

    def __init__(self, *outs):
        self.outs = list(outs)
        self.reqs = []

    def __call__(self, req, log):
        self.reqs.append(req)
        log({"role": "fix", "node": req["node"], "fake": True})
        return self.outs.pop(0) if self.outs else None


def make_env():
    tmp = tempfile.mkdtemp(prefix="edg_selftest_")
    for item in COPY:
        shutil.copytree(os.path.join(PROJECT, item), os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
    work = os.path.join(tmp, "work")
    files = {
        "src/alpha/node_a.py": "def handle_cmd(msg):\n    return msg\n\n\nclass Alpha:\n    def run(self):\n        return handle_cmd('a')\n",
        "src/beta/node_b.py": "from alpha.node_a import handle_cmd\n\n\ndef start():\n    handle_cmd('b')\n    handle_cmd('c')\n",
        "src/beta/README.md": "handle_cmd 的說明\n",
        "docs/long.md": "".join(f"第 {i} 行\n" for i in range(1, 51)),
    }
    for rel, text in files.items():
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    os.makedirs(os.path.join(work, "locked", "inner"))
    return tmp, work


def main():
    tmp, work = make_env()
    sys.path.insert(0, tmp)
    os.chdir(tmp)
    import ollama
    ollama.list = lambda: {"models": []}
    ollama.show = lambda *a, **k: {"capabilities": []}
    from agent_core import edg
    from agent_core.agent import SkillAgent
    from agent_core.schemas import EDG_FIX_SCHEMA
    agent = SkillAgent(model="fake-model")
    agent.current_cwd = work

    def run(graph, fixer=None):
        return edg.Executor(agent, fixer=fixer or FakeFixer()).start(graph)

    def node(job, nid):
        return job["nodes"][nid]

    def t_validate():
        def problems(graph):
            return edg.validate(agent.tools_dir, graph)[0]
        ok = {"goal": "g", "nodes": [{"id": "a", "tool": "search_text", "args": ["x", "src"]},
                                     {"id": "b", "tool": "view_file", "args": [{"from": "a", "field": "path"}], "depends_on": ["a"]},
                                     {"id": "c", "kind": "judgment", "goal": "看結果", "depends_on": ["b"]}]}
        p, specs, order = edg.validate(agent.tools_dir, ok)
        assert p == [] and order == ["a", "b", "c"] and specs["view_file"]["script"] == "cat_cmd.py", (p, order)
        cases = [
            ({"nodes": ok["nodes"]}, "缺少 goal"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "nope_tool"}]}, "沒有 'nope_tool'"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "docker_containers"}]}, "不寫收據"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "search_text", "args": ["x"]},
                                     {"id": "b", "tool": "view_file", "args": [{"from": "a", "field": "path"}]}]}, "depends_on 要有 a"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "search_text", "args": ["x"]},
                                     {"id": "b", "tool": "view_file", "args": [{"from": "a", "field": "lines"}], "depends_on": ["a"]}]},
             "收據項目沒有 lines"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "search_text", "args": ["x"]},
                                     {"id": "j", "kind": "judgment", "goal": "看", "depends_on": ["a"]},
                                     {"id": "b", "tool": "list_dir", "depends_on": ["j"]}]}, "不能依賴判斷節點"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "list_dir", "depends_on": ["b"]},
                                     {"id": "b", "tool": "list_dir", "depends_on": ["a"]}]}, "循環"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "list_dir", "expect": ["ok"]}]}, "expect 只能是"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "list_dir"}, {"id": "a", "tool": "list_dir"}]}, "id 重複"),
            ({"goal": "g", "nodes": [{"id": "a", "tool": "list_dir", "args": [3]}]}, "參數只能是字串"),
        ]
        for graph, want in cases:
            got = problems(graph)
            assert any(want in x for x in got), (want, got)
        before = len(agent.trajectory)
        job = run({"goal": "g", "nodes": [{"id": "a", "tool": "list_dir", "args": ["src"]}, {"id": "b", "tool": "nope_tool"}]})
        assert job["status"] == "invalid" and job["problems"] and len(agent.trajectory) == before, "圖沒過檢查就一個都不執行"

    def t_chain_binding():
        before = len(agent.trajectory)
        job = run({"goal": "找 handle_cmd 定義在哪", "nodes": [
            {"id": "find", "tool": "find_file", "args": ["node_", "src", "--type", "f"], "why": "找節點的程式"},
            {"id": "defs", "tool": "code_ast_reader", "args": [{"from": "find", "field": "path"}], "depends_on": ["find"]},
            {"id": "pick", "kind": "judgment", "goal": "哪一個檔案定義了 handle_cmd", "depends_on": ["defs"]}]})
        assert job["status"] == "judgment", (job["status"], job["stops"])
        assert node(job, "find")["state"] == "done" and node(job, "defs")["state"] == "done"
        insts = node(job, "defs")["instances"]
        assert sorted(os.path.basename(i["args"][0]) for i in insts) == ["node_a.py", "node_b.py"], insts
        assert node(job, "defs")["each"]["instances"] == 2 and node(job, "defs")["each"]["from"] == "find"
        runs = agent.trajectory[before:]
        assert [r["script"] for r in runs] == ["find_file_cmd.py", "code_ast_reader_cmd.py", "code_ast_reader_cmd.py"], runs
        assert all(r.get("receipt") and r.get("result_file") for r in runs), "每一次都走主對話同一條路：存檔、收據、軌跡"
        ids = [i["attempts"][-1]["result_id"] for i in insts]
        assert job["judgments"] == [{"node": "pick", "goal": "哪一個檔案定義了 handle_cmd", "inputs": [{"node": "defs", "results": ids}]}]
        d = os.path.join(agent.script_dir, "logs", "edg_jobs", job["id"])
        saved = json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))
        assert saved["status"] == "judgment" and saved["graph"]["nodes"][0]["why"] == "找節點的程式"
        receipt = json.load(open(os.path.join(d, insts[0]["attempts"][0]["receipt_file"]), encoding="utf-8"))
        assert receipt["tool"] == "code_ast_reader" and receipt["status"] == "pass"
        events = open(os.path.join(d, "events.jsonl"), encoding="utf-8").read()
        assert "開始執行決策圖" in events and "執行完：judgment" in events
        assert agent.current_cwd == work, "跑完工作目錄換回主對話的"

    def t_expect_and_complete():
        job = run({"goal": "g", "nodes": [{"id": "s", "tool": "search_text", "args": ["no_such_word_zz", "src"]}]})
        assert job["status"] == "stopped" and node(job, "s")["state"] == "unexpected", node(job, "s")
        assert "預期 pass" in node(job, "s")["reason"] and job["stops"][0]["node"] == "s"
        job = run({"goal": "有沒有人用（0 筆也是答案）", "nodes": [
            {"id": "s", "tool": "search_text", "args": ["no_such_word_zz", "src"], "expect": ["pass", "empty"]}]})
        assert job["status"] == "done", job["stops"]
        job = run({"goal": "g", "nodes": [{"id": "v", "tool": "view_file", "args": ["docs/long.md", "--lines", "10"], "complete": True}]})
        assert node(job, "v")["state"] == "unexpected" and "不完整" in node(job, "v")["reason"], node(job, "v")
        job = run({"goal": "g", "nodes": [{"id": "v", "tool": "view_file", "args": ["docs/long.md", "--lines", "10"]}]})
        assert job["status"] == "done", "沒有要求完整時，讀一段就算做完"

    def t_fix_precheck():
        fixer = FakeFixer({"reason": "--type 只能是 f 或 d", "fixable": True, "args": ["node_", "src", "--type", "f"]})
        before = len(agent.trajectory)
        job = run({"goal": "找節點的程式", "question": "使用者原本的問題", "nodes": [
            {"id": "find", "tool": "find_file", "args": ["--type", "file", "node_", "src"], "why": "列出節點的程式"}]}, fixer)
        inst = node(job, "find")["instances"][0]
        assert job["status"] == "done" and inst["fixed"] and inst["fix"]["accepted"], inst
        assert inst["attempts"][0]["check"] == "pre" and inst["attempts"][0]["error_kind"] == "args", "執行前的檢查擋下來，沒有執行"
        assert len(agent.trajectory) == before + 1, "只有修好的那一次真的執行"
        req = fixer.reqs[0]
        assert req["kind"] == "args" and req["stage"] == "pre" and req["goal"] == "找節點的程式" and req["why"] == "列出節點的程式"
        assert "--type" in req["error"] and req["args"] == ["--type", "file", "node_", "src"]
        assert "receipt:" not in req["spec"] and "parameters:" not in req["spec"] and "# 語法" in req["spec"], "規格是給模型看的那一份"
        assert "使用者原本的問題" not in json.dumps(req, ensure_ascii=False), "修正只給規格、錯誤、子目標（D5）"
        calls = open(os.path.join(agent.script_dir, "logs", "edg_jobs", job["id"], "calls.jsonl"), encoding="utf-8").read()
        assert '"fake": true' in calls

    def t_fix_rejected():
        g = {"goal": "看檔案", "nodes": [{"id": "v", "tool": "view_file", "args": ["docs/missing.md"]}]}
        cases = [({"reason": "r", "fixable": True, "args": ["docs/missing.md"]}, "參數沒有改"),
                 ({"reason": "r", "fixable": True, "args": ["a.md", "b.md"]}, "沒有通過檢查"),
                 ({"reason": "要換工具", "fixable": False, "args": []}, "修不好：要換工具"),
                 ({"reason": "r", "fixable": True, "args": ['"docs/long.md"']}, "多了 shell 的引號"),
                 (None, "沒有回覆")]
        for out, want in cases:
            fixer = FakeFixer(out)
            job = run(g, fixer)
            inst = node(job, "v")["instances"][0]
            assert job["status"] == "stopped" and inst["state"] == "failed" and want in inst["reason"], (want, inst)
            assert len(inst["attempts"]) == 1 and len(fixer.reqs) == 1 and fixer.reqs[0]["stage"] == "run"
        g2 = {"goal": "在 src/beta 搜「handle cmd」", "nodes": [{"id": "s", "tool": "search_text", "args": ["handle", "cmd", "src/beta"]}]}
        fixer = FakeFixer({"reason": "合併關鍵字、改搜整個目錄", "fixable": True, "args": ["handle cmd", "."]})
        inst = node(run(g2, fixer), "s")["instances"][0]
        assert inst["state"] == "failed" and "範圍放大" in inst["reason"] and len(inst["attempts"]) == 1, inst
        assert edg.widened("grep_cmd.py", {"paths": {"rule": "inside"}}, ["x", "src/beta"], ["x", "src/beta/node_b.py"], work) is None
        assert edg.widened("grep_cmd.py", {"paths": {"rule": "inside"}}, ["x", "src/alpah"], ["x", "src/alpha"], work) is None, "拼錯改成隔壁的不算放大"
        assert edg.widened("find_file_cmd.py", {"path": {"rule": "inside"}}, ["x", "src/beta"], ["x", "src"], work), "find_file 也一樣"
        fixer = FakeFixer({"reason": "合併關鍵字", "fixable": True, "args": ["handle_cmd", "src/beta"]})
        assert node(run(g2, fixer), "s")["state"] == "done", "範圍不變的修正照常重跑"
        fixer = FakeFixer({"reason": "r", "fixable": True, "args": ["docs/also_missing.md"]}, {"reason": "again", "fixable": True, "args": ["docs/long.md"]})
        job = run(g, fixer)
        inst = node(job, "v")["instances"][0]
        assert inst["state"] == "failed" and "修正之後還是錯" in inst["reason"] and len(inst["attempts"]) == 2, inst
        assert len(fixer.reqs) == 1, "每個節點只修一次"

    def t_env_not_fixed():
        if os.geteuid() == 0:
            raise Skip("root 讀得到沒有權限的目錄")
        locked = os.path.join(work, "locked")
        os.chmod(locked, 0)
        try:
            fixer = FakeFixer({"reason": "r", "fixable": True, "args": ["."]})
            job = run({"goal": "列目錄", "nodes": [{"id": "l", "tool": "list_dir", "args": ["locked"]}]}, fixer)
        finally:
            os.chmod(locked, 0o755)
        inst = node(job, "l")["instances"][0]
        assert inst["state"] == "failed" and inst["attempts"][0]["error_kind"] == "env" and not fixer.reqs, inst

    def t_timeout_narrow():
        assert edg.narrowed("grep_cmd.py", ["x", "src"], ["x", "src", "--include", "*.py"], {"include": {"rule": "added"}}, work)[0]
        assert edg.narrowed("grep_cmd.py", ["x", "src"], ["x", "src/alpha"], {"paths": {"rule": "inside"}}, work)[0]
        assert not edg.narrowed("grep_cmd.py", ["x", "src"], ["x", "docs"], {"paths": {"rule": "inside"}}, work)[0]
        assert not edg.narrowed("grep_cmd.py", ["x", "src"], ["y", "src/alpha"], {"paths": {"rule": "inside"}}, work)[0]
        assert not edg.narrowed("grep_cmd.py", ["x", "src"], ["x", "src", "-w"], {"paths": {"rule": "inside"}}, work)[0]
        real = agent.run_script
        calls = []

        def first_times_out(script, args, raw=""):
            calls.append(list(args))
            if len(calls) == 1:
                agent.last_receipt, agent.last_result_id = {"status": "error", "error_kind": "timeout"}, None
                return "[ERROR] 搜尋逾時（30 秒內沒有搜完，也還沒有找到任何一筆）。下一步：縮小路徑、加 --include。"
            return real(script, args, raw)
        agent.run_script = first_times_out
        try:
            g = {"goal": "找 handle_cmd 在 Python 程式裡的用法", "nodes": [{"id": "s", "tool": "search_text", "args": ["handle_cmd", "src"]}]}
            fixer = FakeFixer({"reason": "只搜 .py", "fixable": True, "args": ["handle_cmd", "src", "--include", "*.py"]})
            job = run(g, fixer)
            inst = node(job, "s")["instances"][0]
            assert job["status"] == "done" and inst["fixed"] and calls[1] == ["handle_cmd", "src", "--include", "*.py"], inst
            assert fixer.reqs[0]["kind"] == "timeout" and set(fixer.reqs[0]["narrow"]) == {"paths", "include"}
            calls.clear()
            fixer = FakeFixer({"reason": "換關鍵字", "fixable": True, "args": ["handle", "src/alpha"]})
            job = run(g, fixer)
            inst = node(job, "s")["instances"][0]
            assert inst["state"] == "failed" and "不是規格列出的縮小方式" in inst["reason"] and len(calls) == 1, inst
            calls.clear()
            fixer = FakeFixer({"reason": "r", "fixable": True, "args": ["src/alpha"]})
            job = run({"goal": "列目錄", "nodes": [{"id": "l", "tool": "list_dir", "args": ["src"]}]}, fixer)
            inst = node(job, "l")["instances"][0]
            assert inst["state"] == "failed" and "規格沒有列逾時時的縮小方式" in inst["reason"] and not fixer.reqs, inst
        finally:
            agent.run_script = real

    def t_blocked_and_independent():
        job = run({"goal": "g", "nodes": [
            {"id": "bad", "tool": "view_file", "args": ["docs/missing.md"]},
            {"id": "after", "tool": "list_dir", "args": ["src"], "depends_on": ["bad"]},
            {"id": "other", "tool": "list_dir", "args": ["docs"]}]}, FakeFixer({"reason": "r", "fixable": False, "args": []}))
        assert node(job, "bad")["state"] == "failed" and node(job, "after")["state"] == "blocked" and node(job, "other")["state"] == "done"
        assert job["status"] == "stopped" and {s["node"] for s in job["stops"]} == {"bad", "after"}, job["stops"]
        assert "bad" in node(job, "after")["reason"]

    def t_dedupe_cap_reuse():
        before = len(agent.trajectory)
        job = run({"goal": "g", "nodes": [
            {"id": "s", "tool": "search_text", "args": ["handle_cmd", "src/beta/node_b.py"]},
            {"id": "v", "tool": "view_file", "args": [{"from": "s", "field": "path"}], "depends_on": ["s"]},
            {"id": "v2", "tool": "view_file", "args": [os.path.join(work, "src/beta/node_b.py")], "depends_on": ["v"]}]})
        assert job["status"] == "done", job["stops"]
        each = node(job, "v")["each"]
        assert each["items"] == 3 and each["instances"] == 1, ("同一個檔案三行命中，只看一次", each)
        reused = node(job, "v2")["instances"][0]["attempts"][0]
        assert reused.get("reused") and reused["result_id"] == node(job, "v")["instances"][0]["attempts"][0]["result_id"], reused
        assert len(agent.trajectory) == before + 2, "同一個工具＋同樣的參數只跑一次"
        keep = edg.EDG_EACH_MAX
        edg.EDG_EACH_MAX = 1
        try:
            g = {"goal": "g", "nodes": [{"id": "s", "tool": "search_text", "args": ["handle_cmd", "src", "--include", "*.py"]},
                                        {"id": "a", "tool": "code_ast_reader", "args": [{"from": "s", "field": "path"}], "depends_on": ["s"]}]}
            job = run(g)
            st = node(job, "a")
            assert st["state"] == "done" and st["each"]["instances"] == 2 and st["each"]["ran"] == 1 and "只跑了前 1 個" in st["reason"], st
            g["nodes"][1]["complete"] = True
            assert node(run(g), "a")["state"] == "unexpected", "要完整的結果時，沒跑完就不算做完"
        finally:
            edg.EDG_EACH_MAX = keep

    def t_guard_resume():
        real = agent.guard_check

        def guard(parsed):
            if "locked" in parsed["action"]["args"]:
                return {"skill": "list_dir", "script": "ls_cmd.py", "command": "scripts/ls_cmd.py " + parsed["action"]["args"], "reason": "測試用"}
            return real(parsed)
        agent.guard_check = guard
        try:
            g = {"goal": "g", "nodes": [{"id": "a", "tool": "list_dir", "args": ["src"]},
                                        {"id": "b", "tool": "list_dir", "args": ["locked"], "depends_on": ["a"]}]}
            ex = edg.Executor(agent, fixer=FakeFixer())
            job = ex.start(g)
            assert job["status"] == "need_user" and job["need_user"]["node"] == "b" and "需要你確認" in job["need_user"]["text"], job
            assert node(job, "a")["state"] == "done" and node(job, "b")["state"] == "need_user"
            before = len(agent.trajectory)
            job = edg.Executor(agent, fixer=FakeFixer()).resume(job["id"], approve=True)
            assert job["status"] == "done" and node(job, "b")["state"] == "done" and len(agent.trajectory) == before + 1, job
            job = edg.Executor(agent, fixer=FakeFixer()).start(g)
            job = edg.Executor(agent, fixer=FakeFixer()).resume(job["id"], approve=False)
            assert job["status"] == "stopped" and node(job, "b")["state"] == "failed", node(job, "b")
            assert "沒有同意" in node(job, "b")["reason"]
        finally:
            agent.guard_check = real

    def t_model_fixer():
        seen = {}

        def fake_chat(**kw):
            seen.update(kw)
            return {"message": {"content": json.dumps({"reason": "只搜 .py", "fixable": True, "args": ["k", "src", "--include", "*.py"]})}}
        ollama.chat = fake_chat
        spec = edg.load_spec(agent.tools_dir, "search_text")
        logs = []
        req = {"job": "j", "node": "s", "tool": "search_text", "spec": edg.skill_spec.for_model(spec["text"]), "args": ["k", "src"],
               "error": "[ERROR] 搜尋逾時", "kind": "timeout", "stage": "run", "goal": "子目標的字", "why": "這一步的字",
               "narrow": spec["contract"]["narrow"]}
        out = edg.ModelFixer(agent)(req, logs.append)
        assert out["fixable"] and out["args"][-1] == "*.py", out
        system, user = seen["messages"][0]["content"], seen["messages"][1]["content"]
        assert "修正「一個工具呼叫」的參數" in system and seen["format"] == EDG_FIX_SCHEMA and seen["model"] == "fake-model"
        for want in ("子目標的字", "這一步的字", "【工具】search_text", '["k", "src"]', "[ERROR] 搜尋逾時", "逾時，還沒有任何結果",
                     "- 路徑：換成原本路徑裡面的", "- --include：多加一項"):
            assert want in user, (want, user)
        assert "\nreceipt:" not in user and "\nnarrow:" not in user
        assert logs and logs[0]["role"] == "fix" and logs[0]["response"] and logs[0]["error"] is None
        ollama.chat = lambda **kw: {"message": {"content": "不是 JSON"}}
        logs.clear()
        assert edg.ModelFixer(agent)(dict(req, kind="args", narrow=None), logs.append) is None and logs[0]["error"] == "回覆不是 JSON"

    def t_eval_cases():
        sys.path[:0] = [HERE, os.path.join(PROJECT, "evals", "repo")]
        try:
            import cases
            import run as edg_run
        finally:
            del sys.path[:2]
        for c in cases.CASES:
            p = edg.validate(agent.tools_dir, {"goal": c["goal"], "nodes": [dict(c["node"], id="n")]})[0]
            assert p == [] and c["want"] in ("fixed", "not_fixable") and c["set"] in ("main", "holdout"), (c["id"], p)
            assert (c["want"] == "fixed") == bool(c.get("receipt")), (c["id"], "修得好的題目要核對收據的欄位（含範圍）")
        assert {c["set"] for c in cases.CASES} == {"main", "holdout"}
        ok = cases.receipt_ok
        assert ok({"paths": ["/s/amr_x/hw"]}, {"paths": {"endswith_all": "/hw"}})[0]
        assert not ok({"paths": ["/s/amr_x"]}, {"paths": {"endswith_all": "/hw"}})[0], "範圍放大要擋"
        assert not ok({"paths": []}, {"paths": {"endswith_all": "/hw"}})[0]
        assert ok({"pattern": "Emergency Stop"}, {"pattern": {"ci": "emergency stop"}})[0] and not ok({"type": "d"}, {"type": "f"})[0]

        def job(state, fixed=False, fix=None, attempts=1, receipt=None):
            inst = {"state": state, "fixed": fixed, "fix": fix, "attempts": [{"args": ["a"]}] * attempts}
            return {"nodes": {"n": {"state": state, "reason": "r", "instances": [inst]}}, "_receipt": receipt}
        fixed_case = {"want": "fixed", "receipt": {"type": "f"}}
        assert edg_run.judge(fixed_case, job("done", True, receipt={"type": "f"}))[0]
        assert not edg_run.judge(fixed_case, job("done", True, receipt={"type": "d"}))[0]
        assert not edg_run.judge(fixed_case, job("done", False, receipt={"type": "f"}))[0], "沒有經過修正就成功不算（題目的參數本來就錯）"
        nf = {"want": "not_fixable"}
        assert edg_run.judge(nf, job("failed", fix={"fixable": False, "reason": "要換工具"}))[0]
        assert not edg_run.judge(nf, job("done", True, fix={"fixable": True}, attempts=2))[0], "修不好的硬修成功也不算"
        sys.path.insert(0, os.path.join(PROJECT, "evals"))
        try:
            import phase_check as pc
        finally:
            del sys.path[0]
        real_load = pc.load_baseline
        pc.load_baseline = lambda name: {"models": {"m": {"per": {"a": [3, 3], "b": [1, 3]}, "sets": {"main": [4, 6]}}}} if name == "edg" else None
        try:
            same = {"model": "m", "per": {"a": [3, 3], "b": [2, 3]}, "sets": {"main": [5, 6]}}
            assert pc.compare_edg(same)[2] == "✅" and pc.compare_edg(same)[0] == "主要 5/6", pc.compare_edg(same)
            worse = {"model": "m", "per": {"a": [2, 3], "b": [1, 3], "c": [1, 1]}, "sets": {"main": [4, 7]}}
            text, base, verdict, notes = pc.compare_edg(worse)
            assert verdict == "⚠️" and notes == ["a：2/3（基準 3/3）", "c：基準裡沒有"], notes
        finally:
            pc.load_baseline = real_load

    tests = [("檢查圖：id、依賴、循環、工具要寫收據、帶入的來源與欄位、判斷節點不被依賴、expect", t_validate),
             ("照圖執行、從收據帶入參數（一項一個實例）、判斷節點交回中階；走主對話同一條路（存檔、收據、軌跡）、job 存檔", t_chain_binding),
             ("守門照收據：expect（0 筆算不算答案）、complete（不完整算不合預期）", t_expect_and_complete),
             ("第 1 級：執行前的參數檢查擋下來 → 修一次 → 執行；修正只拿到規格、錯誤、子目標", t_fix_precheck),
             ("第 1 級：程式核對修正（沒改、過不了檢查、多了 shell 的引號、修不好、沒回覆、範圍放大都不重跑）；修完還是錯就往上報，只修一次", t_fix_rejected),
             ("第 1 級：環境的錯（沒有權限）不修，往上報", t_env_not_fixed),
             ("第 1 級：逾時只照規格的 narrow 縮小（加 --include、換成裡面的路徑）；規格沒列的工具不修", t_timeout_narrow),
             ("依賴的節點沒成功就跳過；不相干的節點照跑", t_blocked_and_independent),
             ("帶入的參數去重、實例的上限（要完整時不算做完）；同一個工具＋同樣的參數只跑一次", t_dedupe_cap_reuse),
             ("確認關卡：停下來（need_user）→ 同意後接回同一個節點；拒絕就往上報", t_guard_resume),
             ("修正的模型：prompt 在 prompts/edg/、schema、記進 calls.jsonl；回覆不是 JSON 就不修", t_model_fixer),
             ("第 1 級的真模型評測：每一題的圖都過得了檢查；核對收據的欄位與範圍（範圍放大要擋）；修不好的題目要往上交；階段驗證跟基準比", t_eval_cases)]
    passed = skipped = 0
    failed = []
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"✅ {name}")
        except Skip as e:
            skipped += 1
            print(f"⏭️ {name}：略過（{e}）")
        except Exception as e:      # noqa: BLE001
            failed.append((name, traceback.format_exc()))
            print(f"❌ {name}：{e}")
    for name, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{passed}/{len(tests) - skipped} 通過" + (f"，{skipped} 個略過" if skipped else ""))
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
