"""中階（agent_core/mid.py，新架構 D10 第 3 步的 3a）的離線自我測試：假的模型（挑技能、合約照劇本回）、真的工具與低階執行器（幾秒）。

領域與複合技能的規格（解析、給模型時拿掉給程式看的部分、寫錯的擋下來）、合約的核對（原文要在問題裡、值照種類對原文；沒過的交回修一次）、
排圖（if 群組、名稱清單一項一組、節點的 if）、補參數（預設值、路徑找不到時自己查、剛好一個就補、好幾個問使用者、必填的問使用者、接回）、
執行與報告（定義、呼叫、每個檔案的數量、總數、#編號）、第 2 級（加節點重排、不收斂、問範圍附各子目錄的筆數、熔斷）、
確認關卡停下來與接回、存檔（每一版的圖與節點的狀態、回退、問使用者的問題與回答、報告、模型呼叫）、真模型評測的題目（evals/mid/cases.py）、
Web 的拓撲圖（web_app/topology.py 整理的資料、/topology 頁面與 /api/topology/* 的路由）。

    python3 evals/mid/selftest.py
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts", "web_app", "vision"]


class Skip(Exception):
    pass


class FakeModel:
    """照劇本回（role → 依序回的 dict；None＝沒有回覆）；記下每一次的 (role, system, user, schema)。"""

    def __init__(self, **script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def __call__(self, role, system, user, schema, predict, log):
        self.calls.append({"role": role, "system": system, "user": user, "schema": schema, "predict": predict})
        log({"role": role, "fake": True})
        outs = self.script.get(role) or []
        return outs.pop(0) if outs else None


def cell(quote="", value=""):
    return {"quote": quote, "value": value}


def make_env():
    tmp = tempfile.mkdtemp(prefix="mid_selftest_")
    for item in COPY:
        shutil.copytree(os.path.join(PROJECT, item), os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
    work = os.path.join(tmp, "work")
    files = {
        "src/alpha/node_a.py": "def handle_cmd(msg):\n    return msg\n\n\nclass Alpha:\n    def run(self):\n        return handle_cmd('a')\n",
        "src/beta/node_b.py": "from alpha.node_a import handle_cmd\n\n\ndef start():\n    handle_cmd('b')\n    handle_cmd('c')  # handle_cmd 註解\n",
        "src/beta/README.md": "handle_cmd 的說明\n",
        "src/gamma/tests/test_g.py": "def test_one():\n    pass\n\n\ndef test_two():\n    handle_cmd(1)\n",
        "src/dup/x.py": "y = 1\n", "lib/dup/z.py": "z = 2\n", "src/beta/notes.py": "# note_only 只在註解裡\nx = 'note_only'\n",
        "logs/run1.log": "E9001 start\nE9001 again\nok\n", "logs/run2.log": "E9001\n", "logs/note.txt": "E9001 in notes\n",
        "locked/m.py": "handle_cmd = 1\n",
    }
    for rel, text in files.items():
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return tmp, work


def write_domain(base, name, skills, tools=("search_text", "find_file", "code_ast_reader")):
    """測試用的領域：skills＝{名稱: 規格全文}。"""
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    index = [f"# {name}：測試", "", "測試用的領域。", "", "## 複合技能"] + [f"- [{n}]({n}.md) — 測試" for n in skills]
    index += ["", "## 工具"] + [f"- [{t}](../tools/{t}.md)" for t in tools]
    with open(os.path.join(d, "SKILLS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index) + "\n")
    for n, text in skills.items():
        with open(os.path.join(d, f"{n}.md"), "w", encoding="utf-8") as f:
            f.write(text)


def skill_text(params, nodes, fallbacks, subs=("search_text", "code_ast_reader"), depends=(), answers=("位置", "數量")):
    return ("---\ntype: Skill\ntitle: 測試技能\ndescription: 測試用\nversion: 1.0.0\n"
            f"answers: {json.dumps(list(answers), ensure_ascii=False)}\n"
            f"topology: {json.dumps({'depends_on': list(depends), 'sub_skills': list(subs)}, ensure_ascii=False)}\n"
            f"parameters: {json.dumps(params, ensure_ascii=False)}\n---\n\n# 什麼時候用\n測試。\n\n"
            f"# 骨架\n```json\n{json.dumps({'nodes': nodes}, ensure_ascii=False)}\n```\n\n"
            f"# 回退\n```json\n{json.dumps(fallbacks, ensure_ascii=False)}\n```\n\n# 策略與 SOP\n1. 測試。\n")


NAME_P = {"name": "name", "type": "name", "required": True, "desc": "名稱", "ask": "要查哪個名稱？"}
PATH_P = {"name": "path", "type": "path", "default": ".", "desc": "範圍"}


def main():
    tmp, work = make_env()
    sys.path.insert(0, tmp)
    os.chdir(tmp)
    import ollama
    ollama.list = lambda: {"models": []}
    ollama.show = lambda *a, **k: {"capabilities": []}
    from agent_core import edg, mid, skill_spec
    from agent_core.agent import SkillAgent
    agent = SkillAgent(model="fake-model")
    agent.current_cwd = work

    def py_usage(name_quote, name, path_quote="", path="", **more):
        return FakeModel(select=[{"understanding": "找名稱", "skill": "py_usage", "reason": "問 Python 的名稱"}],
                         contract=[{"understanding": "u", "name": cell(name_quote, name), "path": cell(path_quote, path), "exclude": cell()}],
                         **more)

    def run(question, model, **kw):
        return mid.Worker(agent, model=model, fixer=lambda req, log: None, **kw).start(question)

    def saved(job, name="job.json"):
        p = os.path.join(agent.script_dir, "logs", "mid_jobs", job["id"], name)
        with open(p, encoding="utf-8") as f:
            return json.load(f) if name.endswith(".json") else f.read()

    # ------------------------------------------------------------------------------------------------------------
    def t_domain():
        d = mid.load_domain(agent.base_path, agent.tools_dir, "repo_analysis")
        assert d["problems"] == [] and list(d["skills"]) == ["py_usage", "count_in_scope"], d["problems"]
        assert "不包含" in d["intro"] and "code_ast_reader" in d["tools"]
        with open(os.path.join(agent.base_path, "repo_analysis", "SKILLS.md"), encoding="utf-8") as f:
            index = f.read()
        for name, spec in d["skills"].items():
            assert f"- [{name}]({name}.md) — {spec['meta']['description']}\n" in index, (name, "SKILLS.md 的說明要跟規格的 description 一樣")
            model_text = skill_spec.for_model(spec["text"])
            assert "topology:" not in model_text and "parameters:" not in model_text and "# 骨架" not in model_text and "# 回退" not in model_text
            assert "# 什麼時候用" in model_text and "# 策略與 SOP" in model_text and model_text.startswith("---\ntype: Skill")
        tool_text = open(os.path.join(agent.tools_dir, "search_text.md"), encoding="utf-8").read()
        assert "# 語法" in skill_spec.for_model(tool_text), "工具規格照舊（沒有〈骨架〉〈回退〉）"
        base = tempfile.mkdtemp(prefix="mid_domain_", dir=tmp)
        good_nodes = [{"id": "a", "tool": "search_text", "args": ["{name}", "{path}"], "expect": ["pass", "empty"]}]
        cases = [
            (skill_text([NAME_P, PATH_P], [{"id": "a", "tool": "find_file", "args": ["{name}"]}], []), "不在 topology 的 sub_skills"),
            (skill_text([NAME_P], [{"id": "a", "tool": "search_text", "args": ["{nope}"]}], []), "參數 nope 沒有宣告"),
            (skill_text([NAME_P, {"name": "opt", "type": "text", "desc": "d"}], [{"id": "a", "tool": "search_text", "args": ["{opt}"]}], []),
             "opt 可能沒有值"),
            (skill_text([NAME_P, {"name": "ex", "type": "names", "desc": "d"}],
                        [{"id": "a", "tool": "search_text", "args": ["{name}", {"if": "name", "args": ["--exclude-dir", "{ex}"]}]}], []),
             "名稱清單 ex 要放在"),
            (skill_text([NAME_P], [{"id": "j", "kind": "judgment", "goal": "看"}], []), "判斷節點第一版還沒接上"),
            (skill_text([NAME_P, PATH_P], good_nodes, [], depends=["other"]), "depends_on"),
            (skill_text([NAME_P, PATH_P], good_nodes, [{"id": "f", "when": {"node": "zz", "status": "empty"}, "change": {"ask": "path"}, "say": "s"}]),
             "when 要寫 node"),
            (skill_text([NAME_P, PATH_P], good_nodes, [{"id": "f", "when": {"node": "a", "status": "empty"}, "change": {"ask": "path", "add": []},
                                                        "say": "s"}]), "change 要是 add"),
            (skill_text([NAME_P, PATH_P], [dict(good_nodes[0], report="標題")], [], subs=("search_text", "list_dir")), None),
            (skill_text([dict(NAME_P, ask="")], good_nodes, []), "必填的參數要寫 ask"),
            (skill_text([NAME_P, PATH_P], good_nodes, [], answers=()), "answers 要是"),
            (skill_text([NAME_P, PATH_P], good_nodes, [], answers=("位置", "別的")), "answers 要是"),
            (skill_text([NAME_P, PATH_P], [{"id": "a", "tool": "code_ast_reader", "args": ["{path}"], "report": "x"}], []), "能當報告的是"),
            (skill_text([NAME_P, PATH_P], [{"id": "a", "tool": "search_text", "args": ["{name}"]},
                                          {"id": "b", "tool": "code_ast_reader", "args": [{"from": "a", "field": "lines"}], "depends_on": ["a"]}], []),
             "排出的圖：b：search_text 的收據項目沒有 lines"),
        ]
        for k, (text, want) in enumerate(cases):
            write_domain(base, f"d{k}", {"s": text}, tools=("search_text", "find_file", "code_ast_reader", "list_dir"))
            got = mid.load_domain(base, agent.tools_dir, f"d{k}")["problems"]
            assert (want is None and got == []) or (want and any(want in x for x in got)), (k, want, got)
        write_domain(base, "bad_json", {"s": skill_text([NAME_P], good_nodes, []).replace('"nodes"', "nodes")})
        assert any("〈骨架〉的 JSON 寫錯了" in x for x in mid.load_domain(base, agent.tools_dir, "bad_json")["problems"])
        assert mid.load_domain(base, agent.tools_dir, "nope")["problems"] == ["沒有 skills_system/nope/SKILLS.md"]

    def t_verify():
        v = mid.verify_param
        src = "fih 的程式（pkg/sub/，不含 test、docs）裡，誰呼叫 do_thing？要看 Python 檔、檔名 test_ 開頭的 .py、名稱 test 開頭的 def"
        name = {"name": "name", "type": "name"}
        assert v(name, "誰呼叫 do_thing", "do_thing", src) == ("do_thing", None)
        assert v(name, "", "", src) == (None, None), "沒提到"
        assert "不在問題或子目標裡" in v(name, "誰呼叫 do_other", "do_other", src)[1], "抄的原文要在問題裡"
        assert "要是一個名稱" in v(name, "誰呼叫 do_thing", "x.do_thing", src)[1]
        assert "要是一個名稱" in v(name, "誰呼叫 do_thing", "do_other", src)[1], "名稱要在抄的原文裡"
        assert v(name, "「do_thing」", "`do_thing`", "誰呼叫「do_thing」？")[0] == "do_thing", "引號不算"
        glob = {"name": "files", "type": "glob"}
        assert v(glob, "要看 Python 檔", "*.py", src) == ("*.py", None)
        assert v(glob, "檔名 test_ 開頭的 .py", "test_*.py", src) == ("test_*.py", None)
        assert "「yaml」不在" in v(glob, "要看 Python 檔", "*.yaml", src)[1], "原文沒有的字不能加"
        text = {"name": "keyword", "type": "text"}
        assert v(text, "名稱 test 開頭的 def", "def test", src) == ("def test", None), "每一段字都在原文裡就好（順序可以換）"
        path = {"name": "path", "type": "path"}
        assert v(path, "（pkg/sub/，", "./pkg/sub/", src) == ("pkg/sub", None)
        assert "裡的「src」不是" in v(path, "（pkg/sub/，", "src/pkg/sub", src)[1], "不能自己補上層目錄"
        assert v(path, "pkg 的 sub/ 底下", "pkg/sub/", "pkg 的 sub/ 底下有幾個") == ("pkg/sub", None), "原文的「a 的 b/」就是 a/b"
        assert "不是抄的原文" in v(path, "pkg 的 sub/ 底下", "pkg 的 sub", "pkg 的 sub/ 底下有幾個")[1], "路徑的一段不能有空白"
        names = {"name": "exclude", "type": "names"}
        assert v(names, "不含 test、docs", "test、docs", src) == (["test", "docs"], None)
        assert "「tool」不在" in v(names, "不含 test、docs", "test, tool", src)[1]
        ca = mid.check_answer
        assert ca({"name": "path", "type": "path"}, "src/beta/", work) == ("src/beta", None)
        assert "找不到" in ca({"name": "path", "type": "path"}, "nowhere", work)[1]
        assert ca({"name": "n", "type": "name"}, "a.b", work)[1] and ca({"name": "n", "type": "names"}, "a、b", work) == (["a", "b"], None)

    def t_expand():
        nodes = [{"id": "f", "if": "files", "tool": "find_file", "args": ["{files}", "{path}"]},
                 {"id": "h", "if": "kw", "tool": "search_text",
                  "args": ["{kw}", "{path}", {"if": "files", "args": ["--include", "{files}"]}, {"if": "ex", "args": ["--exclude-dir", "{ex}"]}]},
                 {"id": "r", "tool": "code_ast_reader", "args": [{"from": "h", "field": "path"}], "depends_on": ["h"], "why": "看 {path}"}]
        out, omitted = mid.expand_nodes(nodes, {"kw": "E1", "path": "logs", "ex": ["a", "b"]})
        assert [n["id"] for n in out] == ["h", "r"] and omitted == {"f"}, (out, omitted)
        assert out[0]["args"] == ["E1", "logs", "--exclude-dir", "a", "--exclude-dir", "b"] and "if" not in out[0], out[0]
        assert out[1]["args"] == [{"from": "h", "field": "path"}] and out[1]["why"] == "看 logs"
        out, omitted = mid.expand_nodes(nodes, {"files": "*.log", "path": "."})
        assert [n["id"] for n in out] == ["f"] and omitted == {"h", "r"}, "依賴沒排的節點也不排"

    def t_py_usage_flow():
        before = len(agent.trajectory)
        model = py_usage("誰呼叫 handle_cmd", "handle_cmd", "src 裡", "src")
        job = run("src 裡的 Python 程式，handle_cmd 定義在哪？誰呼叫 handle_cmd？", model)
        assert job["status"] == "done" and job["skill"] == "py_usage", (job["status"], job.get("result"))
        assert job["params"]["name"] == {"value": "handle_cmd", "quote": "誰呼叫 handle_cmd", "source": "question"}
        assert job["params"]["path"]["value"] == "src" and job["params"]["path"]["checked"] and "exclude" not in job["params"]
        g = job["graphs"][0]
        assert g["version"] == 1 and g["cause"] is None and [n["id"] for n in g["graph"]["nodes"]] == ["hits", "refs"]
        assert g["graph"]["nodes"][0]["args"] == ["handle_cmd", "src", "-w", "--include", "*.py"], g["graph"]["nodes"][0]
        assert g["nodes"]["hits"]["state"] == "done" and g["nodes"]["refs"]["instances"] == 3 and g["status"] == "done", g["nodes"]
        report = job["result"]["report"]
        for want in ("- 定義（1）：\n  - src/alpha/node_a.py:1　def handle_cmd，行 1-2", "- 呼叫：總共 4 次（3 個檔案）",
                     "    - src/beta/node_b.py：2 次", "    - src/alpha/node_a.py:7（在 Alpha.run）：return handle_cmd('a')",
                     "    - src/beta/node_b.py:6（在 start）：handle_cmd('c')", "- import（1）：", "- 出處：#"):
            assert want in report, (want, report)
        assert "README.md" not in report and "src/beta/node_b.py:1（模組層）：from alpha.node_a import handle_cmd" in report, "import 不算呼叫"
        assert [r["script"] for r in agent.trajectory[before:]].count("code_ast_reader_cmd.py") == 3
        assert saved(job)["status"] == "done" and saved(job, "report.md") == report
        roles = [c["role"] for c in model.calls]
        assert roles == ["select", "contract"], roles
        sel = model.calls[0]
        assert sel["schema"]["properties"]["skill"]["enum"] == ["py_usage", "count_in_scope", "none", "out_of_domain"]
        assert sel["schema"]["properties"]["asks"]["items"]["enum"] == ["位置", "數量", "內容"] and list(sel["schema"]["properties"])[1] == "asks"
        assert "  答得了：位置、數量\n" in sel["user"] and "  答得了：數量\n" in sel["user"], sel["user"]
        assert "什麼時候用：問題提到程式裡的一個名稱" in sel["user"] and "不包含" in sel["user"] and "【這一層的子目標】" not in sel["user"]
        con = model.calls[1]
        assert list(con["schema"]["properties"]) == ["understanding", "name", "path", "exclude"]
        assert "- name（名稱，必填）：問題問到的那個名稱本身" in con["user"] and "- path（路徑，沒有提到就用 .）" in con["user"], con["user"]
        assert "- exclude（名稱清單，沒有提到就不用）" in con["user"] and "【選好的複合技能】py_usage" in con["user"]
        events = open(os.path.join(agent.script_dir, "logs", "mid_jobs", job["id"], "events.jsonl"), encoding="utf-8").read()
        assert "挑技能：py_usage" in events and "第 1 版的圖" in events and "中階結束：做完" in events
        calls = open(os.path.join(agent.script_dir, "logs", "mid_jobs", job["id"], "calls.jsonl"), encoding="utf-8").read()
        assert calls.count('"fake": true') == 2
        note = run("src/beta 裡誰呼叫 note_only？", py_usage("誰呼叫 note_only", "note_only", "src/beta 裡", "src/beta"))
        assert note["status"] == "done", ("只在註解裡提到的檔案：AST 0 處也是答案", note["result"]["report"])
        assert "- 只在註解或字串裡提到、程式裡沒有用到的檔案（1）：src/beta/notes.py" in note["result"]["report"], note["result"]["report"]

    def t_contract_fix():
        model = FakeModel(select=[{"understanding": "u", "skill": "py_usage", "reason": "r"}],
                          contract=[{"understanding": "u", "name": cell("誰呼叫 handle_cmd", "handle_cmd"), "path": cell("在 src/beta 目錄", "src/beta"),
                                     "exclude": cell("不含 tests", "tests")}],
                          contract_fix=[{"understanding": "u", "path": cell("src/beta 裡", "src/beta")}])
        job = run("src/beta 裡誰呼叫 handle_cmd？（不含 tests）", model)
        assert job["status"] == "done" and job["params"]["path"]["value"] == "src/beta", job["params"]
        assert job["params"]["exclude"]["value"] == ["tests"]
        assert [(r["param"], r["round"]) for r in job["rejected"]] == [("path", 1)] and "不在問題或子目標裡" in job["rejected"][0]["why"]
        fix = model.calls[2]
        assert fix["role"] == "contract_fix" and list(fix["schema"]["properties"]) == ["understanding", "path"], "只重寫沒過的參數"
        assert "【上一次沒有通過核對的參數：只重寫這幾個】" in fix["user"] and "「在 src/beta 目錄」不在問題或子目標裡" in fix["user"], fix["user"]
        model = FakeModel(select=[{"understanding": "u", "skill": "py_usage", "reason": "r"}],
                          contract=[{"understanding": "u", "name": cell(), "path": cell("src/alpha 裡", "src/alpha")}],
                          contract_fix=[{"understanding": "u", "name": cell("誰呼叫 handle_cmd", "handle_cmd")}])
        job = run("src/alpha 裡誰呼叫 handle_cmd？", model)
        assert job["status"] == "done" and job["params"]["name"]["value"] == "handle_cmd", "漏了的必填參數也交回修一次"
        fix = model.calls[2]
        assert list(fix["schema"]["properties"]) == ["understanding", "name"] and "- name：必填，但沒有寫" in fix["user"], fix["user"]
        model = FakeModel(select=[{"understanding": "u", "skill": "py_usage", "reason": "r"}],
                          contract=[{"understanding": "u", "name": cell("誰呼叫 run_it", "run_it")}], contract_fix=[None])
        job = run("誰呼叫 handle_cmd？", model)
        assert job["status"] == "need_user" and job["need_user"]["param"] == "name" and job["need_user"]["question"] == "要查哪一個函式、類別或變數？"
        assert [(r["param"], r["round"]) for r in job["rejected"]] == [("name", 1)], "修的那一次沒有回覆：當成沒提到"

    def t_ask_and_resume():
        model = FakeModel(select=[{"understanding": "u", "skill": "py_usage", "reason": "r"}],
                          contract=[{"understanding": "u", "name": cell(), "path": cell("src 裡", "src")}])
        job = run("src 裡那個函式誰在用？", model)
        assert job["status"] == "need_user" and job["need_user"] == {"kind": "param", "param": "name", "question": "要查哪一個函式、類別或變數？",
                                                                    "candidates": []}, job["need_user"]
        assert saved(job)["status"] == "need_user" and job["graphs"] == []
        w = mid.Worker(agent, model=FakeModel(), fixer=lambda req, log: None)
        job = w.resume(job["id"], answer="a.b")
        assert job["status"] == "need_user" and "要是一個名稱" in job["need_user"]["error"], job["need_user"]
        job = w.resume(job["id"], answer="handle_cmd")
        assert job["status"] == "done" and job["params"]["name"] == {"value": "handle_cmd", "source": "user", "checked": True}
        assert "呼叫：總共 4 次" in job["result"]["report"] and "name＝handle_cmd（使用者回答）" in job["result"]["report"]
        asked = saved(job)["asked"]
        assert len(asked) == 1 and asked[0]["param"] == "name" and asked[0]["version"] == 0 and asked[0]["answer"] == "handle_cmd", asked
        assert asked[0]["answered"] and asked[0]["errors"][0]["answer"] == "a.b" and "要是一個名稱" in asked[0]["errors"][0]["error"], asked
        assert w.resume(job["id"], answer="x")["status"] == "done", "沒有在等使用者就照原樣回"

    def t_fetch():
        job = run("beta 裡誰呼叫 handle_cmd？", py_usage("誰呼叫 handle_cmd", "handle_cmd", "beta 裡", "beta"))
        assert job["status"] == "done" and job["params"]["path"]["value"] == "src/beta" and job["params"]["path"]["source"] == "fetch"
        assert job["auto_filled"] == [{"param": "path", "given": "beta", "value": "src/beta", "edg_job": job["fetches"][0]["edg_job"]}]
        assert job["fetches"][0]["exact"] == ["src/beta"] and job["edg_job"] != job["fetches"][0]["edg_job"], "查參數是另一個低階工作"
        assert "- 自己補的：path＝src/beta（原文寫「beta」，查到剛好一個）" in job["result"]["report"]
        job = run("dup 裡誰呼叫 handle_cmd？", py_usage("誰呼叫 handle_cmd", "handle_cmd", "dup 裡", "dup"))
        assert job["status"] == "need_user" and job["need_user"]["candidates"] == ["lib/dup", "src/dup"], job["need_user"]
        assert "有好幾個" in job["need_user"]["question"]
        job = mid.Worker(agent, model=FakeModel(), fixer=lambda req, log: None).resume(job["id"], answer="src/dup")
        assert job["status"] == "done" and job["params"]["path"]["value"] == "src/dup" and job["graphs"][0]["cause"] is None, "還沒排過圖：不算重排"
        job = run("nowhere_zz 裡誰呼叫 handle_cmd？", py_usage("誰呼叫 handle_cmd", "handle_cmd", "nowhere_zz 裡", "nowhere_zz"))
        assert job["status"] == "need_user" and job["need_user"]["candidates"] == [] and "找不到「nowhere_zz」" in job["need_user"]["question"]

    def t_outside_scope():
        before = len(agent.trajectory)
        job = run("src/alpha 裡誰呼叫 start？", py_usage("誰呼叫 start", "start", "src/alpha 裡", "src/alpha"))
        assert job["status"] == "done" and job["replans"] == 1 and len(job["graphs"]) == 2, (job["status"], job["fallbacks"])
        assert job["fallbacks"][0]["fallback"] == "outside_scope" and job["fallbacks"][0]["result"] == "replanned"
        g2 = job["graphs"][1]
        assert g2["cause"] == {"kind": "fallback", "fallback": "outside_scope", "say": job["fallbacks"][0]["say"], "added": ["wider"]}
        assert [n["id"] for n in g2["graph"]["nodes"]] == ["hits", "refs", "wider"] and g2["nodes"]["wider"]["state"] == "done"
        assert job["graphs"][0]["nodes"]["hits"]["state"] == "done" and "wider" not in job["graphs"][0]["nodes"], "第一版的狀態留著"
        report = job["result"]["report"]
        assert "## 範圍外提到這個名稱的檔案" in report and "    - src/beta/node_b.py：1 筆" in report and "- 呼叫：總共 0 次" in report, report
        assert "## 第 2 級（回退）\n- outside_scope：" in report and "（重排）" in report
        scripts = [r["script"] for r in agent.trajectory[before:]]
        assert scripts == ["grep_cmd.py", "grep_cmd.py"], ("hits 不重跑；refs 沒有可以帶入的檔案", scripts)
        ej = json.load(open(os.path.join(agent.script_dir, "logs", "edg_jobs", job["edg_job"], "job.json"), encoding="utf-8"))
        assert ej["replans"][0]["added"] == ["wider"] and set(ej["replans"][0]["kept"]) == {"hits", "refs"}

    def t_not_converging():
        job = run("誰呼叫 nothing_like_this？", py_usage("誰呼叫 nothing_like_this", "nothing_like_this"))
        assert job["status"] == "done" and job["replans"] == 0 and len(job["graphs"]) == 1, (job["status"], job["fallbacks"])
        assert job["fallbacks"][0]["result"] == "no_new_nodes" and "排出來的節點都跑過了" in job["result"]["report"]
        assert "- 定義（0）：沒有" in job["result"]["report"]

    def t_too_many_ask():
        real = edg.EDG_EACH_MAX
        edg.EDG_EACH_MAX = 2
        try:
            job = run("src 裡誰呼叫 handle_cmd？", py_usage("誰呼叫 handle_cmd", "handle_cmd", "src 裡", "src"))
            assert job["status"] == "need_user" and job["need_user"]["fallback"] == "too_many_files", (job["status"], job["fallbacks"])
            assert job["need_user"]["param"] == "path" and job["need_user"]["candidates"][0] == "src/beta（3 筆）", job["need_user"]
            assert set(job["need_user"]["candidates"]) == {"src/beta（3 筆）", "src/alpha（2 筆）", "src/gamma（1 筆）"}
            job = mid.Worker(agent, model=FakeModel(), fixer=lambda req, log: None).resume(job["id"], answer="src/beta")
        finally:
            edg.EDG_EACH_MAX = real
        assert job["status"] == "done" and job["replans"] == 1 and job["graphs"][1]["cause"] == {"kind": "user", "param": "path", "value": "src/beta"}
        assert job["graphs"][1]["graph"]["nodes"][0]["args"][1] == "src/beta" and "呼叫：總共 2 次（1 個檔案）" in job["result"]["report"]
        assert [f["result"] for f in job["fallbacks"]] == ["ask"]
        asked = job["asked"][0]
        assert asked["fallback"] == "too_many_files" and asked["version"] == 1 and asked["answer"] == "src/beta" and len(asked["candidates"]) == 3, asked

    def t_circuit_break():
        nodes = [{"id": "a", "tool": "search_text", "args": ["{name}", "{path}"], "expect": ["pass", "empty"]}]
        fbs = [{"id": f"f{k}", "when": {"node": "a", "status": "empty"},
                "change": {"add": [{"id": f"x{k}", "tool": "search_text", "args": ["{name}", ".", "-C", str(k)], "expect": ["pass", "empty"]}]},
                "say": f"換做法 {k}"} for k in range(1, 5)]
        write_domain(agent.base_path, "cb", {"loop": skill_text([NAME_P, PATH_P], nodes, fbs, subs=("search_text",))}, tools=("search_text",))
        model = FakeModel(select=[{"understanding": "u", "skill": "loop", "reason": "r"}],
                          contract=[{"understanding": "u", "name": cell("找 zz_nothing", "zz_nothing"), "path": cell()}])
        job = mid.Worker(agent, domain="cb", model=model, fixer=lambda req, log: None).start("找 zz_nothing")
        assert job["status"] == "circuit_break" and job["replans"] == 3 and len(job["graphs"]) == 4, (job["status"], job["replans"])
        assert [f["result"] for f in job["fallbacks"]] == ["replanned", "replanned", "replanned", "circuit_break"]
        assert "熔斷" in job["result"]["report"] and "還要套用 f4" in job["result"]["note"]

    def t_count_in_scope():
        model = FakeModel(select=[{"understanding": "u", "skill": "count_in_scope", "reason": "r"}],
                          contract=[{"understanding": "u", "keyword": cell("E9001 幾次", "E9001"), "files": cell("所有的 log", "*.log"),
                                     "path": cell("logs 目錄", "logs"), "exclude": cell()}])
        job = run("logs 目錄裡所有的 log，E9001 幾次？", model)
        assert job["status"] == "done", job["result"]
        nodes = job["graphs"][0]["graph"]["nodes"]
        assert [n["id"] for n in nodes] == ["files", "hits"] and nodes[1]["args"] == ["E9001", "logs", "--include", "*.log", "-l"], nodes
        report = job["result"]["report"]
        for want in ("- 名稱符合「*.log」的檔案：2 個（從 logs 開始找）", "    - logs/run1.log：2 筆", "    - logs/run2.log：1 筆",
                     "- 總共 3 筆（2 個檔案）", "- 搜尋「E9001」，範圍：logs；只看 *.log"):
            assert want in report, (want, report)
        assert "note.txt" not in report
        model = FakeModel(select=[{"understanding": "u", "skill": "count_in_scope", "reason": "r"}],
                          contract=[{"understanding": "u", "keyword": cell(), "files": cell("檔名 test_ 開頭的 .py", "test_*.py"),
                                     "path": cell(), "exclude": cell("不含 gamma", "gamma")}])
        job = run("有幾個檔名 test_ 開頭的 .py（不含 gamma）？", model)
        assert job["status"] == "done" and [n["id"] for n in job["graphs"][0]["graph"]["nodes"]] == ["files"]
        assert "- 名稱符合「test_*.py」的檔案：0 個（從 . 開始找）；不含 gamma 裡的 1 個" in job["result"]["report"], job["result"]["report"]
        model = FakeModel(select=[{"understanding": "u", "skill": "count_in_scope", "reason": "r"}],
                          contract=[{"understanding": "u", "keyword": cell(), "files": cell(), "path": cell(), "exclude": cell()}])
        job = run("數一下", model)
        assert job["status"] == "need_user" and job["need_user"]["param"] == "keyword" and "至少要有一個" in job["need_user"]["question"]

    def t_select_outcomes():
        for out, status in (({"understanding": "u", "skill": "none", "reason": "沒有技能讀長文件"}, "no_skill"),
                            ({"understanding": "u", "skill": "out_of_domain", "reason": "問正在跑的容器"}, "out_of_domain"),
                            ({"understanding": "u", "skill": "made_up", "reason": "r"}, "failed"), (None, "failed")):
            job = run("問題", FakeModel(select=[out]))
            assert job["status"] == status and job["graphs"] == [] and job["result"]["status"] == status, (status, job["status"])
            assert saved(job, "report.md").startswith(f"# 中階的結果：{mid.STATUS_TEXT[status]}")
        assert "沒有技能讀長文件" in run("問題", FakeModel(select=[{"understanding": "u", "skill": "none", "reason": "沒有技能讀長文件"}]))["result"]["note"]
        job = run("規格書寫了什麼？", FakeModel(select=[{"understanding": "u", "asks": ["內容", "數量"], "skill": "count_in_scope", "reason": "r"}]))
        assert job["status"] == "no_skill" and job["selection"]["rejected"] == "count_in_scope", "選的技能答不了問題要的「內容」"
        assert "問題要的「內容」它答不了（它答得了：數量）" in job["result"]["note"] and job["selection"]["asks"] == ["內容", "數量"]

    def t_guard():
        real = agent.guard_check

        def guard(parsed):
            if "locked" in parsed["action"]["args"] and "grep_cmd" in parsed["action"]["command"]:
                return {"skill": "search_text", "script": "grep_cmd.py", "command": "scripts/grep_cmd.py " + parsed["action"]["args"], "reason": "測試用"}
            return real(parsed)
        agent.guard_check = guard
        try:
            job = run("locked 裡誰用 handle_cmd？", py_usage("誰用 handle_cmd", "handle_cmd", "locked 裡", "locked"))
            assert job["status"] == "need_user" and job["need_user"]["kind"] == "guard" and job["need_user"]["node"] == "hits", job["need_user"]
            job = mid.Worker(agent, model=FakeModel(), fixer=lambda req, log: None).resume(job["id"], approve=True)
        finally:
            agent.guard_check = real
        assert job["status"] == "done" and "- 指定（1）：" in job["result"]["report"], job["result"]["report"]
        assert job["asked"][0]["kind"] == "guard" and job["asked"][0]["node"] == "hits" and job["asked"][0]["approve"] is True, job["asked"]
        ej = json.load(open(os.path.join(agent.script_dir, "logs", "edg_jobs", job["edg_job"], "job.json"), encoding="utf-8"))
        decisions = ej["nodes"]["hits"]["instances"][0]["decisions"]
        assert len(decisions) == 1 and decisions[0]["approve"] is True and decisions[0]["text"], decisions

    def t_topology_view():
        from web_app import topology
        view = lambda j: topology.job_view("logs", f"mid_jobs/{j['id']}", root=tmp)
        # 兩版的圖：範圍裡沒有 → 回退加 wider；第一版看得到回退（marks），第二版從條件的節點畫虛線（extra_edges）
        two = run("src/alpha 裡誰呼叫 start？", py_usage("誰呼叫 start", "start", "src/alpha 裡", "src/alpha"))
        v = view(two)
        assert v["kind"] == "mid" and v["status_text"] == "做完" and v["originals"] is True and len(v["versions"]) == 2, v["status"]
        v1, v2 = v["versions"]
        assert [(m["type"], m["from"], m["to_version"], m["added"]) for m in v1["marks"]] == [("replanned", "hits", 2, ["wider"])], v1["marks"]
        assert v1["change"] is None and v2["change"]["added"] == ["wider"] and set(v2["change"]["kept"]) == {"hits", "refs"}, v2["change"]
        assert [(e["from"], e["to"], e["type"], e["fallback"]) for e in v2["extra_edges"]] == [("hits", "wider", "fallback", "outside_scope")]
        assert "wider" not in v1["nodes"] and v1["nodes"]["hits"]["box"]["state"] == "done" and v1["nodes"]["hits"]["box"]["statuses"] == ["empty"]
        assert v1["nodes"]["refs"]["box"]["each"]["instances"] == 0 and v2["nodes"]["wider"]["box"]["results"], v2["nodes"]["wider"]
        att = v1["nodes"]["hits"]["detail"]["instances"][0]["attempts"][0]
        assert v1["nodes"]["hits"]["box"]["results"] == [att["result_id"]]
        assert topology.receipt("logs", v["edg"]["ref"], att["receipt_file"], root=tmp)["status"] == "empty", "收據全文"
        assert "## 第 2 級（回退）" in v["report"] and v["events"] and [c["role"] for c in v["calls"]] == ["select", "contract"]
        assert "report" not in v["result"], "報告另外給一份，不重複"
        # 問使用者（回退）→ 回答 → 照新的參數重新排：第一版換掉的節點，從低階的 replans 找回當時的狀態
        real = edg.EDG_EACH_MAX
        edg.EDG_EACH_MAX = 2
        try:
            job = run("src 裡誰呼叫 handle_cmd？", py_usage("誰呼叫 handle_cmd", "handle_cmd", "src 裡", "src"))
            mark = view(job)["versions"][0]["marks"][0]
            assert mark["type"] == "ask" and mark["ask"]["candidates"][0] == "src/beta（3 筆）" and "answer" not in mark["ask"], mark
            assert "to_version" not in mark and view(job)["need_user"]["fallback"] == "too_many_files"
            job = mid.Worker(agent, model=FakeModel(), fixer=lambda req, log: None).resume(job["id"], answer="src/beta")
        finally:
            edg.EDG_EACH_MAX = real
        v = view(job)
        m = v["versions"][0]["marks"][0]
        assert m["ask"]["answer"] == "src/beta" and m["to_version"] == 2 and v["versions"][1]["cause"]["kind"] == "user", m
        first = v["versions"][0]["nodes"]["hits"]["detail"]["instances"][0]["args"]
        second = v["versions"][1]["nodes"]["hits"]["detail"]["instances"][0]["args"]
        assert first[1] == "src" and second[1] == "src/beta", (first, second)
        assert v["versions"][1]["change"]["rerun"] == ["hits", "refs"] and v["versions"][1]["change"]["kept"] == [], v["versions"][1]["change"]
        each = v["versions"][0]["nodes"]["refs"]["box"]["each"]
        assert each["instances"] == 3 and each["ran"] == 2, "第一版：帶入的超過上限"
        # 確認關卡：等確認時節點看得到；同意之後看得到決定
        real_guard = agent.guard_check
        agent.guard_check = lambda parsed: ({"skill": "search_text", "script": "grep_cmd.py", "reason": "測試用",
                                             "command": "scripts/grep_cmd.py " + parsed["action"]["args"]}
                                            if "locked" in parsed["action"]["args"] and "grep_cmd" in parsed["action"]["command"]
                                            else real_guard(parsed))
        try:
            job = run("locked 裡誰用 handle_cmd？", py_usage("誰用 handle_cmd", "handle_cmd", "locked 裡", "locked"))
            box = view(job)["versions"][0]["nodes"]["hits"]["box"]
            assert box["state"] == "need_user" and box["decisions"] == [] and view(job)["asked"][0]["kind"] == "guard", box
            job = mid.Worker(agent, model=FakeModel(), fixer=lambda req, log: None).resume(job["id"], approve=True)
        finally:
            agent.guard_check = real_guard
        box = view(job)["versions"][0]["nodes"]["hits"]["box"]
        assert job["status"] == "done" and box["decisions"][0]["approve"] is True and box["state"] == "done", (job["status"], box)
        assert view(job)["asked"][0]["approve"] is True and view(job)["versions"][0]["status"] == "done"
        # 自己查路徑：另一個低階工作，附在中階的工作裡，清單不另外列
        job = run("beta 裡誰呼叫 handle_cmd？", py_usage("誰呼叫 handle_cmd", "handle_cmd", "beta 裡", "beta"))
        f = view(job)["fetches"][0]
        assert f["ref"] == f"edg_jobs/{job['fetches'][0]['edg_job']}" and f["nodes"]["fetch"]["box"]["state"] == "done", f
        listed = {j["ref"] for j in topology.jobs("logs", root=tmp)}
        assert f"mid_jobs/{job['id']}" in listed and f["ref"] not in listed and f"edg_jobs/{job['edg_job']}" not in listed
        # 沒有技能：沒有圖，看得到停在挑技能
        job = run("問題", FakeModel(select=[{"understanding": "u", "skill": "none", "reason": "沒有技能讀長文件"}]))
        v = view(job)
        assert v["versions"] == [] and v["selection"]["skill"] == "none" and v["result"]["note"] == "沒有技能讀長文件" and v["asked"] == []
        # 單獨的低階工作（沒有被中階用到）列在清單裡
        ej = edg.Executor(agent, fixer=lambda req, log: None).start(
            {"goal": "g", "nodes": [{"id": "n", "tool": "search_text", "args": ["handle_cmd", "src"], "expect": ["pass", "empty"]}]})
        assert f"edg_jobs/{ej['id']}" in {j["ref"] for j in topology.jobs("logs", root=tmp)}
        v = topology.job_view("logs", f"edg_jobs/{ej['id']}", root=tmp)
        assert v["kind"] == "edg" and v["versions"][0]["nodes"]["n"]["box"]["state"] == "done" and v["goal"] == "g"
        # 評測結果的來源：題目底下的 mid_jobs、edg_jobs，或低階評測直接放的 job.json；評測的 #編號 原文看不到
        logs = os.path.join(tmp, "logs")
        res = os.path.join(tmp, "evals", "results")
        shutil.copytree(os.path.join(logs, "mid_jobs", two["id"]), os.path.join(res, "20990101_000000_mid_fake", "logs", "q_1", "mid_jobs", two["id"]))
        shutil.copytree(os.path.join(logs, "edg_jobs", two["edg_job"]), os.path.join(res, "20990101_000000_mid_fake", "logs", "q_1", "edg_jobs", two["edg_job"]))
        shutil.copytree(os.path.join(logs, "edg_jobs", ej["id"]), os.path.join(res, "20990101_000001_edg_fake", "logs", "q_2"))
        os.makedirs(os.path.join(res, "20990101_000002_ops_fake", "logs", "s_1"))
        keys = [s["key"] for s in topology.sources(root=tmp)]
        assert keys[:3] == ["logs", "evals/results/20990101_000001_edg_fake", "evals/results/20990101_000000_mid_fake"], keys
        assert "evals/results/20990101_000002_ops_fake" not in keys, "沒有工作的評測結果不列"
        src = "evals/results/20990101_000000_mid_fake"
        assert [(j["ref"], j["case"], j["versions"]) for j in topology.jobs(src, root=tmp)] == [(f"q_1/mid_jobs/{two['id']}", "q_1", 2)]
        v = topology.job_view(src, f"q_1/mid_jobs/{two['id']}", root=tmp)
        assert v["originals"] is False and v["edg"]["ref"] == f"q_1/edg_jobs/{two['edg_job']}" and len(v["versions"]) == 2
        assert v["versions"][1]["nodes"]["wider"]["box"]["state"] == "done"
        assert [j["ref"] for j in topology.jobs("evals/results/20990101_000001_edg_fake", root=tmp)] == ["q_2"]
        # 路徑一律由程式組：不合規則的回 None（頁面回 404）
        for s, ref in (("logs", "../logs/mid_jobs/x"), ("logs", "mid_jobs/.."), ("logs", f"mid_jobs/{two['id']}/.."), ("evals/results/..", "logs"),
                       ("/etc", "passwd"), ("logs", "a/b/c/d"), ("logs", ""), (None, None), ("evals/results", "x")):
            assert topology.job_view(s, ref, root=tmp) is None, (s, ref)
        assert topology.jobs("evals/results/../..", root=tmp) is None and topology.jobs("/etc", root=tmp) is None
        for rel in ("../job.json", "receipts/../../job.json", "job.json", "receipts/x.txt", None):
            assert topology.receipt("logs", f"edg_jobs/{two['edg_job']}", rel, root=tmp) is None, rel

    def t_topology_http():
        import threading
        import urllib.error
        import urllib.parse
        import urllib.request
        from http.server import ThreadingHTTPServer
        from web_app import server
        run("問題", FakeModel(select=[{"understanding": "u", "skill": "none", "reason": "r"}]))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ConsoleHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def get(path):
            try:
                with urllib.request.urlopen(base + path, timeout=10) as r:
                    return r.status, r.read().decode("utf-8"), r.headers.get("Content-Type", "")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8"), e.headers.get("Content-Type", "")
        try:
            status, body, ctype = get("/topology?src=logs")
            assert status == 200 and "<title>決策圖</title>" in body and ctype.startswith("text/html"), status
            assert 'href="/topology"' in get("/")[1], "對話頁的標題列有連結"
            status, body, _ = get("/api/topology/sources")
            assert status == 200 and json.loads(body)[0]["key"] == "logs"
            ref = next(j["ref"] for j in json.loads(get("/api/topology/jobs?src=logs")[1]) if j["kind"] == "mid")
            status, body, _ = get(f"/api/topology/job?src=logs&ref={urllib.parse.quote(ref)}")
            assert status == 200 and json.loads(body)["ref"] == ref
            for bad in ("/api/topology/job?src=logs&ref=..%2F..%2Fetc", "/api/topology/jobs?src=%2Fetc", "/api/topology/nothing",
                        f"/api/topology/receipt?src=logs&ref={urllib.parse.quote(ref)}&file=..%2Fjob.json"):
                assert get(bad)[0] == 404, bad
        finally:
            httpd.shutdown()
            httpd.server_close()

    def t_model_caller():
        seen = {}

        class FakeAgent:
            model = "m1"

            def _timed_chat(self, kind, **kw):
                seen.update(kind=kind, **kw)
                return {"message": {"content": seen.get("reply", '{"skill": "x"}')}}
        logs = []
        caller = mid.ModelCaller(FakeAgent())
        out = caller("select", "SYS", "USER", {"type": "object"}, 123, logs.append)
        assert out == {"skill": "x"} and seen["kind"] == "mid_select" and seen["format"] == {"type": "object"}
        assert seen["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}] and seen["options"]["num_predict"] == 123
        assert logs[0]["role"] == "select" and logs[0]["response"] == '{"skill": "x"}' and logs[0]["error"] is None
        seen["reply"] = "not json"
        assert caller("contract", "S", "U", {}, 1, logs.append) is None and logs[1]["error"] == "回覆不是 JSON"

    def t_eval_cases():
        sys.path[:0] = [HERE, os.path.join(PROJECT, "evals", "repo")]
        try:
            import cases
            import questions
        finally:
            del sys.path[:2]
        qs = {q["id"]: q for q in questions.load()["questions"]}
        assert set(cases.LABELS) == set(qs), "每一題都要標該用的複合技能（沒有的寫 none）"
        d = mid.load_domain(agent.base_path, agent.tools_dir, "repo_analysis")
        for qid, lab in cases.LABELS.items():
            assert all(x in list(d["skills"]) + ["none"] for x in cases.wanted(lab)), (qid, lab["skill"])
            names = {p["name"] for x in cases.wanted(lab) if x != "none" for p in d["skills"][x]["parameters"]}
            assert set(lab.get("params", {})) <= names, (qid, set(lab.get("params", {})) - names)
        ok = cases.param_ok
        assert ok("pkg/sub", {"endswith": "sub"}) and not ok("pkg", {"endswith": "sub"}) and ok("x", "x") and not ok("y", "x")
        assert ok(["test", "docs"], {"set": ["docs", "test"]}) and ok(None, {"absent": True}) and not ok("a", {"absent": True})
        assert ok("def test", {"words": ["def", "test"]}) and not ok("test", {"words": ["def", "test"]})
        assert ok("pkg/sub", {"any": ["pkg", "pkg/sub"]}) and not ok("other", {"any": ["pkg"]})
        job = {"status": "done", "skill": "py_usage", "params": {"name": {"value": "f"}, "path": {"value": "pkg/sub"}},
               "result": {"report": "x"}, "fallbacks": [], "graphs": [{}]}
        lab = {"skill": "py_usage", "params": {"name": "f", "path": {"endswith": "sub"}}}
        s = cases.layers(lab, job)
        assert s["skill"] and s["params"] and s["param_misses"] == [], s
        s = cases.layers(lab, dict(job, params={"name": {"value": "g"}}))
        assert s["skill"] and not s["params"] and s["param_misses"] == ["name：g（要的是 'f'）", "path：沒有（要的是 {'endswith': 'sub'}）"], s
        assert cases.layers({"skill": "none"}, dict(job, status="no_skill", skill=None))["skill"]
        sys.path.insert(0, os.path.join(PROJECT, "evals"))
        try:
            import phase_check as pc
        finally:
            del sys.path[0]
        d = tempfile.mkdtemp(prefix="mid_runs_", dir=tmp)
        runs = [{"id": "a", "set": "main", "model": "m", "score": {"skill": True, "params": True, "final": {"passed": True}}},
                {"id": "a", "set": "main", "model": "m", "score": {"skill": True, "params": False, "final": {"passed": False}}},
                {"id": "n", "set": "holdout", "model": "m", "score": {"skill": True, "params": True, "final": None}}]
        with open(os.path.join(d, "runs.jsonl"), "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r) + "\n" for r in runs)
        r = pc.mid_result(d)
        assert r["per"] == {"a": {"skill": [2, 2], "params": [1, 2], "final": [1, 2]}, "n": {"skill": [1, 1], "params": [1, 1]}}, r["per"]
        assert r["sets"]["main"]["final"] == [1, 2] and "final" not in r["sets"]["holdout"]
        assert pc.classify(os.path.join(tmp, "20261118_000000_mid_m")) == "mid"
        real_load = pc.load_baseline
        pc.load_baseline = lambda name: {"models": {"m": {"per": {"a": {"skill": [2, 2], "params": [2, 2], "final": [1, 2]}},
                                                          "sets": {"main": {"skill": [2, 2]}}}}} if name == "mid" else None
        try:
            text, base, verdict, notes = pc.compare_mid(r)
            assert verdict == "⚠️" and notes == ["a 合約：1/2（基準 2/2）", "n：基準裡沒有"], notes
            assert text.startswith("主要 挑技能 2/2、合約 1/2、報告 1/2；保留 挑技能 1/1") and base == "主要 挑技能 2/2", (text, base)
        finally:
            pc.load_baseline = real_load

    tests = [("領域與複合技能的規格：解析、給模型時拿掉給程式看的部分、SKILLS.md 跟規格一致、寫錯的擋下來（含用假參數排一次圖）", t_domain),
             ("合約的核對：原文要在問題裡；名稱、路徑、名稱清單原樣在原文裡；文字與檔案名稱的寫法每一段都在原文裡；使用者的回答", t_verify),
             ("排圖：if 群組（名稱清單一項一組）、節點的 if、依賴沒排的節點也不排", t_expand),
             ("py_usage 走一遍：挑技能 → 合約 → 排圖 → 低階 → 報告（定義、呼叫、每個檔案幾次、總數、import 不算呼叫、#編號）；存檔與模型的輸入", t_py_usage_flow),
             ("合約沒過核對（或漏了必填的參數）：只把這幾個交回修一次；修了還是不對就當成沒提到", t_contract_fix),
             ("必填的參數沒提到：問使用者 → 回答不合法再問 → 回答之後接著做（問了什麼、不合法的回答、最後的回答都記下來）", t_ask_and_resume),
             ("路徑找不到：照 fetch 查一次，剛好一個就自己補（報告寫明）；好幾個或沒有就問使用者", t_fetch),
             ("第 2 級：範圍裡沒有 → 加節點看範圍外；重排只跑新的節點，每一版的狀態都留著", t_outside_scope),
             ("第 2 級：加的節點都跑過了＝不收斂，不重排；0 筆就是答案", t_not_converging),
             ("第 2 級：檔案太多（超過低階的上限）→ 問使用者縮小範圍（附各子目錄的筆數）→ 照回答重新排圖", t_too_many_ask),
             ("第 2 級：重排超過上限就熔斷", t_circuit_break),
             ("count_in_scope：照範圍數（只看的檔案、不含的子目錄由程式扣），每個檔案的筆數與總數；什麼都沒給就問", t_count_in_scope),
             ("挑技能：沒有適合的、不屬於這個領域、清單外、沒有回覆；選的技能答不了問題要的那一種（位置、數量、內容）", t_select_outcomes),
             ("確認關卡：低階停下來 → 中階要問使用者 → 同意後接回（中階記下問了什麼、低階的實例記下決定）", t_guard),
             ("Web 的拓撲圖的資料：每一版的圖與當時的狀態（重排換掉的從低階找回）、跟上一版比、回退與問使用者、確認關卡、自己查路徑、清單、"
              "評測的來源、不合規則的路徑擋下來", t_topology_view),
             ("Web 的拓撲圖：/topology 頁面與 /api/topology/*（找不到、路徑不合規則回 404）；對話頁的標題列有連結", t_topology_http),
             ("模型呼叫：prompt、schema、num_predict、記進 calls.jsonl；回覆不是 JSON 當成沒有回覆", t_model_caller),
             ("中階的真模型評測：每一題都標了該用的複合技能，參數是那個技能的；參數與每一層的核對", t_eval_cases)]
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
            print(f"❌ {name}：{str(e)[:300]}")
    for name, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{passed}/{len(tests) - skipped} 通過" + (f"，{skipped} 個略過" if skipped else ""))
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
