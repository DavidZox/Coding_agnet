"""評測的完整性（離線、幾秒）：模型會讀的文字裡不能有評測世界獨有的名稱。

範例用了評測情境的檔案、名稱、數值時，評測量到的是「會不會抄範例」而不是會不會做（2026-10-24 查 fs_edit_param 時發現：
file_ops 的範例正好是那一題的答案；設計筆記 2.19）。這裡把評測世界的名稱從評測的來源自動取出來（新增情境不用改這裡），
掃模型會讀的文字：

- prompts/ 底下的 .md（prompts/Memory.md 除外：那是使用者的長期記憶，會隨使用改變）、skills_system/SKILLS.md、
  skills_system/tools/*.md；
- agent_core/、vision/、web_app/、skills_system/scripts/ 裡回給模型的字串（用法、[ERROR] 的例子）：程式裡的字串常數，docstring 與
  註解不算；scripts/mock_server.py（開發用的替身，本來就是評測沙盒）不算。

另外檢查 prompts/ 的範本跟程式對得上（2026-10-25 把程式裡給模型的字搬進 prompts/ 之後，設計筆記 2.22）：程式用到的每一則（prompt_files.load
或模組裡的 _t、_x… 這種取一則的小函式）都在、程式填的每個名稱範本裡都有 {名稱}、範本裡沒有沒人用的一則；讀範本的 agent_core/prompt_files.py
本身（取一則、一次填完、讀不到回空字串）。

還有沒人用的程式（2026-11 第 6 階段清掉舊路徑之後，不要再累積）：agent_core、web_app、vision、技能腳本裡定義了卻沒有人用的函式、方法、
類別、模組層的常數，與各檔 import 了卻沒用到的名稱。

還有階段驗證的維運比對（evals/phase_check.py）：基準記每個情境每一次的結果，只跑一部分（2026-11 起維運分成「檔案與調查」與凍結的工具）
時總分跟基準裡同一組情境比；只更新一部分的基準時，其他情境的基準不動。

評測世界的名稱：機器人（tb1…）、工作包（WP_…）、站點（a0…）與語意名稱（組裝線區-2…）、容器、映像、檔案沙盒的路徑、
設定檔裡的設定名稱、錯誤碼、數據的編號（exp_…）。調度系統本身的協定名稱（distribute、handshake_states、threshold_recovery_sec…）
是技能要描述的領域知識，評測沙盒照真的系統做，所以不算（ALLOWED）。範例要用 `<檔案>`、`<名稱>` 或評測世界沒有的名稱
（amr_07、p0、WP_0815、cam_driver、config/camera.yaml…）。

    python3 evals/integrity/selftest.py
"""
import ast
import glob
import json
import os
import re
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
DATASET = os.path.join(PROJECT, "evals", "ops", "dataset")
SOURCES = ["evals/ops/dataset/scenarios.py", "evals/ops/dataset/scenarios_holdout.py", "evals/ops/dataset/scenarios_inv.py",
           "evals/ops/dataset/fs_world.py",
           "evals/ops/dataset/sandbox/sandbox.py", "evals/ops/dataset/sandbox/rmf_sim/rmf_sim.py",
           "evals/chat/scenarios.py"]
# 調度系統與 ROS 2 本身的名稱：評測沙盒照真的系統做，技能規格要描述它們
# （/opt/ros 是 ROS 2 的安裝位置：容器裡的 ros2 指令要先 source 它；TaskAgent 是機器人端回授權的節點；
#  best_effort、keep_last 是 ROS 2 的 QoS，ROS2_topic_pub 要列出可以用的 QoS；/scan 是 ROS 2 雷射慣用的 topic）
ALLOWED = {"ros__parameters", "authorize_timeout_sec", "threshold_recovery_sec", "threshold_ovp_sec", "fleet_name",
           "web_console_url", "manual_trigger_url", "/opt/ros", "TaskAgent", "best_effort", "best-effort", "keep_last", "KeepLast", "/scan"}
SKIP_CODE = {"skills_system/scripts/mock_server.py"}


def _read(rel):
    with open(os.path.join(PROJECT, rel), encoding="utf-8") as f:
        return f.read()


def eval_names():
    """評測世界獨有的名稱 → 種類。"""
    sys.path[:0] = [DATASET, os.path.join(DATASET, "sandbox")]
    try:
        import fs_world
        import sandbox
    finally:
        del sys.path[:2]
    src = {rel: _read(rel) for rel in SOURCES}
    joined = "\n".join(src.values())
    names = {}

    def add(kind, items):
        for x in items:
            x = x.strip()
            if x and x not in ALLOWED:
                names.setdefault(x, kind)

    add("機器人", re.findall(r"\btb\d+\b", joined))
    add("工作包", re.findall(r"\bWP_[A-Za-z0-9_]+\b", joined))
    add("數據", re.findall(r"\bexp_\d{8}_\d{6}\b", joined))
    add("錯誤碼", re.findall(r"\bE\d{4}\b", src["evals/ops/dataset/fs_world.py"]))
    sim = src["evals/ops/dataset/sandbox/rmf_sim/rmf_sim.py"]
    for name, label in re.findall(r'\{"id": \d+, "name": "([^"]*)", "label": "([^"]*)"', sim):
        if re.fullmatch(r"a\d+", name):
            add("站點", [name])
        if label and label != name:
            add("站點的語意名稱", [label] + [p for p in re.split(r"[-：]", label) if len(p) >= 3])
    files = [p for p in fs_world.files() if "/" in p]
    files += re.findall(r'\("fs_\w+", "([\w./-]+/[\w./-]+)"', joined)          # 情境檢查的路徑（建出來的檔案）
    files += re.findall(r'"([\w./-]+/[\w.-]+\.(?:csv|md|yaml|yml|txt|log))"\s*:', joined)   # fs_extra
    files += re.findall(r"(?<![\w.])/(?:etc|opt)/[\w./-]*[\w]", joined)
    add("檔案", files)
    containers = list(sandbox.CONTAINERS) + re.findall(r'"--name",\s*"([\w.-]+)"', joined)
    containers += re.findall(r'\("docker_\w+",\s*"([\w.-]+)"', joined)          # 情境檢查的容器（建出來的）
    containers += re.findall(r'\("([\w.-]+)",\s*"(?:Up|Exited)', joined)          # 主對話評測的假容器清單
    containers += re.findall(r'"([a-z0-9]+_[a-z0-9_]+)"', re.search(r"DOCKER_SET = \[[^\]]*\]", joined).group(0))
    add("容器", containers + ["rmf_sim"])
    add("映像", list(sandbox.IMAGES) + [sandbox.SIM_IMAGE])
    world_text = "\n".join(text for text, _ in fs_world.files().values())
    add("設定名稱", re.findall(r"^\s*-?\s*([a-z]+_[a-z0-9_]+):", world_text, re.M))
    add("真實專案的答案", repo_answer_names())
    return names


def repo_answer_names():
    """真實專案評測（evals/repo/answers.json）答案裡的名稱：檔名、函式與類別、參數、topic、規格書的編號。
    只收答案：題目裡的名稱不算（凍結的調度工具本來就照真的系統描述 distribute 這些名字）；數字、中文、短的通用字（ekf、IDLE）不算。"""
    with open(os.path.join(PROJECT, "evals", "repo", "answers.json"), encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    out = set()
    for q in qs:
        for alt in (a for it in q["items"] for grp in it["all"] for a in grp):
            if len(alt) >= 5 and re.fullmatch(r"[/A-Za-z_][\w./-]*", alt) and re.search(r"[_./-]|[a-z][A-Z]", alt):
                out.add(alt)
    return out


def _pattern(names):
    alts = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(n) for n in alts) + r")(?![\w-])")


def facing_docs():
    docs = glob.glob(os.path.join(PROJECT, "prompts", "**", "*.md"), recursive=True)
    docs = [p for p in docs if os.path.basename(p) != "Memory.md"]
    docs += [os.path.join(PROJECT, "skills_system", "SKILLS.md")]
    docs += glob.glob(os.path.join(PROJECT, "skills_system", "tools", "*.md"))
    return sorted(docs)


def code_strings(path):
    """程式裡的字串常數（f-string 的文字部分也算）→ [(行號, 字串)]；docstring 不算。"""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docs.add(id(first.value))
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def find_leaks(pattern, docs=None, code=None):
    """→ [(相對路徑, 行號, 名稱, 那一行)]"""
    hits = []
    for path in docs if docs is not None else facing_docs():
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                for m in pattern.finditer(line):
                    hits.append((os.path.relpath(path, PROJECT), i, m.group(0), line.strip()[:160]))
    if code is None:
        code = sorted(glob.glob(os.path.join(PROJECT, "agent_core", "*.py")) + glob.glob(os.path.join(PROJECT, "vision", "*.py"))
                      + glob.glob(os.path.join(PROJECT, "web_app", "*.py")) + glob.glob(os.path.join(PROJECT, "skills_system", "scripts", "*.py")))
        code = [p for p in code if os.path.relpath(p, PROJECT) not in SKIP_CODE]
    for path in code:
        for line_no, text in code_strings(path):
            for m in pattern.finditer(text):
                hits.append((os.path.relpath(path, PROJECT), line_no, m.group(0), text.strip()[:160]))
    return hits


CODE_DIRS = ("agent_core", "vision", "web_app")   # 會讀 prompts/ 範本的程式


def _is_load(call):
    f = call.func
    return isinstance(f, ast.Attribute) and f.attr == "load" and isinstance(f.value, ast.Name) and f.value.id == "prompt_files"


def template_uses():
    """程式用到的範本 → (uses, unresolved)。uses：[(程式:行, 範本路徑, 段名, {程式填的名稱})]；段名是 None＝整份檔案。
    看得懂的寫法：prompt_files.load(路徑, 段名, 名稱=…)、模組裡「return prompt_files.load(路徑, key, **fields)」的小函式（_t、_x…）
    加上段名；路徑、段名可以是字串、模組常數或 a if … else b。整份檔案用 f-string 組路徑的（extract/{name}）不算看不懂。"""
    uses, unresolved = [], []
    for d in CODE_DIRS:
        for path in sorted(glob.glob(os.path.join(PROJECT, d, "*.py"))):
            rel = os.path.relpath(path, PROJECT)
            tree = ast.parse(_read(rel))
            consts = {n.targets[0].id: n.value.value for n in tree.body
                      if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                      and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}

            def val(n):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    return [n.value]
                if isinstance(n, ast.Name) and n.id in consts:
                    return [consts[n.id]]
                if isinstance(n, ast.IfExp):
                    a, b = val(n.body), val(n.orelse)
                    return a + b if a is not None and b is not None else None
                return None

            helpers, inside = {}, set()
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef):
                    continue
                body = [b for b in fn.body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
                if len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.Call) and _is_load(body[0].value):
                    c = body[0].value
                    params = [a.arg for a in fn.args.posonlyargs + fn.args.args]
                    paths = val(c.args[0]) if c.args else None
                    if paths and len(c.args) >= 2 and isinstance(c.args[1], ast.Name) and params and c.args[1].id == params[0]:
                        helpers[fn.name] = paths[0]
                        inside.add(id(c))
                    elif isinstance(c.args[0], ast.JoinedStr) and len(c.args) == 1:
                        inside.add(id(c))          # 整份檔案、路徑用 f-string 組的小函式（read_prompt("worker.md")）
            for c in ast.walk(tree):
                if not isinstance(c, ast.Call) or id(c) in inside:
                    continue
                names = {k.arg for k in c.keywords if k.arg}
                where = f"{rel}:{c.lineno}"
                if _is_load(c):
                    if not c.args:
                        unresolved.append(where)
                        continue
                    paths = val(c.args[0])
                    if paths is None:
                        if not (isinstance(c.args[0], ast.JoinedStr) and len(c.args) == 1):
                            unresolved.append(where)
                        continue
                    secs = val(c.args[1]) if len(c.args) > 1 else [None]
                elif isinstance(c.func, ast.Name) and c.func.id in helpers:
                    paths, secs = [helpers[c.func.id]], (val(c.args[0]) if c.args else None)
                else:
                    continue
                if secs is None:
                    unresolved.append(where)
                    continue
                uses += [(where, p, s, names) for p in paths for s in secs]
    return uses, unresolved


def unparsed_importers():
    """import 了 prompt_files、檢查卻一處 prompt_files.load 都沒看到的模組（解析的寫法跟程式對不上了），與 import 它的模組數。
    取代以前的「至少 200 處」：用到的數量會隨程式增減（2026-11-18 拿掉任務引擎少了四十幾處），每個模組各自核對才不靠門檻。"""
    importers, seen = set(), set()
    for d in CODE_DIRS:
        for path in sorted(glob.glob(os.path.join(PROJECT, d, "*.py"))):
            rel = os.path.relpath(path, PROJECT)
            for n in ast.walk(ast.parse(_read(rel))):
                if isinstance(n, ast.ImportFrom) and (any(a.name == "prompt_files" for a in n.names)
                                                      or (n.module or "").endswith("prompt_files")):
                    importers.add(rel)
                elif isinstance(n, ast.Import) and any(a.name.endswith("prompt_files") for a in n.names):
                    importers.add(rel)
                elif isinstance(n, ast.Call) and _is_load(n):
                    seen.add(rel)
    return sorted(importers - seen), len(importers)


# ---------------------------------------------------------------- 沒人用的程式
DEAD_SCAN_DIRS = ("agent_core", "web_app", "vision", "skills_system/scripts")    # 找「定義了沒人用」的範圍
REF_DIRS = DEAD_SCAN_DIRS + ("evals", "test_data/tools")                         # 找引用的範圍（測試、評測工具用到的也算）
REF_FILES = ("Agent_Runner.py", "web_console.py", "web_app/static/index.html")
# 框架照名稱呼叫的（ast.NodeVisitor 的 visit_*、http.server 的 do_GET…）、檔案的進入點：不算沒人用
_CALLED_BY_NAME = re.compile(r"^(visit_\w+|do_(GET|POST|HEAD|PUT|DELETE)|log_message|setUp|tearDown|main|__\w+__)$")
_SKIP_DIRS = {"__pycache__", "results", "archive", "fixtures"}


def _py_files(root, dirs):
    out = []
    for d in dirs:
        for dp, dn, fn in os.walk(os.path.join(root, d)):
            dn[:] = [x for x in dn if x not in _SKIP_DIRS]
            out += [os.path.join(dp, f) for f in fn if f.endswith(".py")]
    return sorted(out)


def dead_definitions(root=PROJECT):
    """[(相對路徑, 行號, 名稱)]：函式、方法、類別、模組層的大寫常數，名稱在引用的範圍裡只出現一次（就是定義的那一次）。
    靜態的粗略比對：名稱出現在字串、註解裡也算有人用（寧可漏也不誤報）；同名的定義互相算引用。"""
    words = {}
    for path in _py_files(root, REF_DIRS) + [os.path.join(root, f) for f in REF_FILES]:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
                words[w] = words.get(w, 0) + 1
    out = []
    for path in _py_files(root, DEAD_SCAN_DIRS):
        tree = ast.parse(open(path, encoding="utf-8").read())
        found = [(n.lineno, n.name) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        found += [(n.lineno, t.id) for n in tree.body if isinstance(n, ast.Assign) for t in n.targets
                  if isinstance(t, ast.Name) and t.id.isupper()]
        out += [(os.path.relpath(path, root), ln, name) for ln, name in found
                if not _CALLED_BY_NAME.match(name) and words.get(name, 0) <= 1]
    return sorted(out)


def unused_imports(root=PROJECT):
    """[(相對路徑, 行號, 名稱)]：import 了卻沒用到的（名稱在那個檔案裡只出現在 import 那裡）；__init__.py、__future__、標了 noqa 的不算。"""
    out = []
    for path in _py_files(root, REF_DIRS):
        if os.path.basename(path) == "__init__.py":
            continue
        src = open(path, encoding="utf-8").read()
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                names = [(a.asname or a.name).split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
                names = [a.asname or a.name for a in node.names if a.name != "*"]
            else:
                continue
            if "noqa" in lines[node.lineno - 1]:
                continue
            out += [(os.path.relpath(path, root), node.lineno, n) for n in names
                    if len(re.findall(rf"(?<![\w.]){re.escape(n)}(?!\w)", src)) <= 1]
    return sorted(out)


def t_dead_code():
    dead = dead_definitions()
    assert not dead, "定義了卻沒有人用（清掉；真的是框架照名稱呼叫的，加進 _CALLED_BY_NAME）：\n" + "\n".join(f"{p}:{ln} {n}" for p, ln, n in dead)
    unused = unused_imports()
    assert not unused, "import 了卻沒用到：\n" + "\n".join(f"{p}:{ln} {n}" for p, ln, n in unused)
    with tempfile.TemporaryDirectory() as d:                     # 抓得到：放一個有沒人用的函式、多餘的 import 的檔案
        os.makedirs(os.path.join(d, "agent_core"))
        with open(os.path.join(d, "agent_core", "x.py"), "w", encoding="utf-8") as f:
            f.write("import json\nimport os\n\n\nclass V:\n    def visit_Name(self, node):\n        return node\n\n\n"
                    "def used():\n    return os.sep\n\n\ndef _never_called():\n    return used()\n")
        assert [n for _, _, n in dead_definitions(d)] == ["V", "_never_called"], dead_definitions(d)
        assert [n for _, _, n in unused_imports(d)] == ["json"], unused_imports(d)


def t_ops_compare():
    sys.path.insert(0, os.path.join(PROJECT, "evals"))
    import phase_check as pc
    one = lambda ok: {"runs": 1, "passed": int(ok), "forbidden": 0, "median_s": 5, "results": [int(ok)]}   # noqa: E731
    three = lambda *r: {"runs": 3, "passed": sum(r), "forbidden": 0, "median_s": 5, "results": list(r)}   # noqa: E731
    base = {"current": {"label": "測試", "per": {"fs_a": three(1, 1, 1), "fs_b": three(1, 0, 1), "inv_c": three(1, 1, 1),
                                                 "dk_d": three(0, 0, 0)}}}
    assert pc.ops_part(["fs_a", "ho_fs_x", "inv_c"]) == "harness" and pc.ops_part(["dk_d", "ho_cx_y"]) == "tools"
    assert pc.ops_part(["fs_a", "dk_d"]) == "all"
    real_load, real_base = pc.load_baseline, pc.BASE
    pc.load_baseline = lambda name: base
    try:
        # 只跑檔案與調查：基準的總分只算這幾個情境（主要每一次 2、1、2；調查與報告 1、1、1），不拿全部情境的總分來比
        _, btxt, verdict, notes = pc.compare_ops({"per": {"fs_a": one(True), "fs_b": one(False), "inv_c": one(True)}})
        assert "主要 2、1、2／2" in btxt and "調查與報告 1、1、1／1" in btxt and "保留" not in btxt and verdict == "✅", (btxt, notes)
        # 低於同一組情境每一次的最低分才列（主要 0 < 1）；基準 3/3 的這次沒過也列
        _, _, verdict, notes = pc.compare_ops({"per": {"fs_a": one(False), "fs_b": one(False), "inv_c": one(True)}})
        assert verdict == "⚠️" and notes[0] == "總分低於基準（同一組情境）的最低分：主要 0 < 1" and "fs_a：0/1 過（基準 3/3）" in notes, notes
    finally:
        pc.load_baseline = real_load
    with tempfile.TemporaryDirectory() as d:   # 只更新一部分：這次有跑的情境換成新的結果，其他情境的基準不動
        pc.BASE = d
        try:
            import json
            name = f"ops_{pc.OPS_MODEL.replace(':', '-')}"
            with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(base, f)
            pc.save_baseline([{"kind": "ops", "key": "ops", "dirs": ["/x/20261117_ops_all_phase"], "per": {"fs_a": one(False)}}], "只跑檔案")
            per = pc.load_baseline(name)["current"]["per"]
            assert per["fs_a"]["results"] == [0] and per["fs_a"]["since"].startswith("只跑檔案") and per["dk_d"]["results"] == [0, 0, 0], per
        finally:
            pc.BASE = real_base


def main():
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
            print(f"✅ {name}")
        except Exception as e:   # noqa: BLE001
            results.append((name, False, traceback.format_exc()))
            print(f"❌ {name}：{e}")

    names = eval_names()
    pattern = _pattern(names)

    def t_names_extracted():
        # 從評測的來源取得到各種名稱（取不到的話下面兩項就是空的檢查）；協定名稱不在裡面
        kinds = set(names.values())
        for kind in ("機器人", "工作包", "數據", "錯誤碼", "站點", "站點的語意名稱", "檔案", "容器", "映像", "設定名稱", "真實專案的答案"):
            assert kind in kinds, f"沒有取到「{kind}」：{sorted(kinds)}"
        for x in ("tb4", "WP_L2", "exp_20261014_084506", "E1203", "a7", "組裝線區-2", "configs/robots.yaml",
                  "configs/nav/nav_params.yaml", "/etc/web_cache.conf", "ops_notes/2026-10-10.md", "web_cache", "talker_box",
                  "scratch_box", "ros2_humble", "ubuntu:24.04", "max_vel_x", "battery_low",
                  "spatio_temporal_scheduler.py", "/rf2o_odom", "TSK-S08"):
            assert x in names, f"沒有取到 {x}"
        assert "distribute" not in names, "真實專案只收答案裡的名稱，題目裡的不收"
        assert not ALLOWED & set(names), ALLOWED & set(names)

    def t_detects_planted():
        # 掃描真的抓得到：放一份含評測名稱的文件與程式，各抓到一次；中性的名稱、docstring 不算
        with tempfile.TemporaryDirectory() as d:
            doc = os.path.join(d, "x.md")
            with open(doc, "w", encoding="utf-8") as f:
                f.write("改一台的值加 `--after \"id: tb4\"`；派 amr_07 從 p0 到 p2；`docker_ctl status cam_driver`\n")
            src = os.path.join(d, "x.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write('"""例：tb1"""\n\ndef f():\n    """tb2"""\n    return f"[ERROR] 例如 set configs/robots.yaml battery_low 18"\n')
            hits = find_leaks(pattern, docs=[doc], code=[src])
            got = sorted(h[2] for h in hits)
            assert got == ["battery_low", "configs/robots.yaml", "tb4"], hits

    def t_docs():
        hits = find_leaks(pattern, code=[])
        assert not hits, ("模型會讀的文件裡有評測世界的名稱（改成 <檔案>、<名稱> 或評測世界沒有的名稱）：\n"
                          + "\n".join(f"  {p}:{i}：{n}（{names[n]}）｜{ln}" for p, i, n, ln in hits))

    def t_code():
        hits = find_leaks(pattern, docs=[])
        assert not hits, ("程式回給模型的字串裡有評測世界的名稱（改成 <名稱> 或評測世界沒有的名稱）：\n"
                          + "\n".join(f"  {p}:{i}：{n}（{names[n]}）｜{ln}" for p, i, n, ln in hits))

    def t_templates():
        sys.path.insert(0, PROJECT)
        try:
            from agent_core import prompt_files
        finally:
            sys.path.remove(PROJECT)
        uses, unresolved = template_uses()
        missing, importers = unparsed_importers()
        assert importers and not missing, f"這幾個模組 import 了 prompt_files，檢查卻看不到它怎麼讀範本（寫法跟程式對不上了）：{missing}"
        assert not unresolved, "這幾處的範本路徑或段名靜態看不出來（段名用字串常數，或 a if … else b）：\n" + "\n".join(unresolved)
        bad = []
        for where, rel, sec, names in uses:
            if not prompt_files.exists(rel, sec):
                bad.append(f"{where}：prompts/{rel}" + (f" 沒有「{sec}」這一則" if sec else " 不存在"))
                continue
            if sec is None:
                continue
            text = prompt_files.sections(_read(os.path.join("prompts", rel)))[sec]
            missing = [n for n in sorted(names) if "{" + n + "}" not in text]
            if missing:
                bad.append(f"{where}：prompts/{rel}「{sec}」裡沒有 {'、'.join('{' + n + '}' for n in missing)}（程式填了，範本沒用到）")
        used = {(rel, sec) for _, rel, sec, _ in uses}
        for path in sorted(glob.glob(os.path.join(PROJECT, "prompts", "**", "*.md"), recursive=True)):
            rel = os.path.relpath(path, os.path.join(PROJECT, "prompts"))
            for sec in prompt_files.sections(_read(os.path.relpath(path, PROJECT))):
                if (rel, sec) not in used:
                    bad.append(f"prompts/{rel}「{sec}」沒有程式用到（拿掉，或接上程式）")
        assert not bad, "\n".join(bad)

    def t_loader():
        sys.path.insert(0, PROJECT)
        try:
            from agent_core import prompt_files
        finally:
            sys.path.remove(PROJECT)
        text = "給人看的說明\n<!-- @a -->\n\n  第一行 {v}\n  第二行\n\n\n<!-- @b -->\nJSON 例：{\"x\": 1}、{名稱}、{v}{w}\n"
        secs = prompt_files.sections(text)
        assert secs == {"a": "\n  第一行 {v}\n  第二行", "b": "JSON 例：{\"x\": 1}、{名稱}、{v}{w}"}, secs   # 開頭的空行留著、最後的換行不算
        assert prompt_files.fill(secs["b"], {"v": "{w}", "w": "W"}) == "JSON 例：{\"x\": 1}、{名稱}、{w}W"   # 一次填完；別的大括號照留
        with tempfile.TemporaryDirectory() as d:
            real = prompt_files.PROMPTS_DIR
            prompt_files.PROMPTS_DIR = d
            try:
                with open(os.path.join(d, "t.md"), "w", encoding="utf-8") as f:
                    f.write(text)
                assert prompt_files.load("t.md", "a", v="1") == "\n  第一行 1\n  第二行"
                assert prompt_files.load("t.md", "b", key="K", section="S", relpath="R") == secs["b"], "名稱叫 key、section、relpath 也行"
                assert prompt_files.load("t.md") == text, "整份檔案照原樣（不去頭尾）"
                assert prompt_files.load("t.md", "nope") == "" and prompt_files.load("none.md") == "" and prompt_files.load("none.md", "a") == ""
                assert prompt_files.exists("t.md", "a") and not prompt_files.exists("t.md", "c") and not prompt_files.exists("none.md")
                with open(os.path.join(d, "t.md"), "w", encoding="utf-8") as f:
                    f.write("<!-- @a -->\n改過了，大小也不一樣\n")
                os.utime(os.path.join(d, "t.md"), None)
                assert prompt_files.load("t.md", "a") == "改過了，大小也不一樣", "檔案改了就重讀（不用重新啟動）"
            finally:
                prompt_files.PROMPTS_DIR = real

    for name, fn in [("從評測的來源取得評測世界的名稱（機器人、工作包、站點、容器、檔案、設定…）；協定名稱不算", t_names_extracted),
                     ("掃描抓得到：文件與程式字串裡的評測名稱各抓到；中性的名稱、docstring 不算", t_detects_planted),
                     ("prompts、SKILLS.md、技能規格沒有評測世界的名稱", t_docs),
                     ("agent_core、vision、web_app 與技能腳本回給模型的字串沒有評測世界的名稱", t_code),
                     ("prompts/ 的範本跟程式對得上：用到的每一則都在、填的名稱範本裡都有、沒有沒人用的一則", t_templates),
                     ("讀範本（agent_core/prompt_files.py）：取一則、一次填完、讀不到回空字串、檔案改了就重讀", t_loader),
                     ("沒人用的程式：定義了卻沒有人用的函式、類別、常數，import 了卻沒用到的（清掉的舊路徑不要再累積）", t_dead_code),
                     ("階段驗證的維運比對：只跑一部分時跟基準裡同一組情境的每一次比；只更新一部分的基準時其他情境不動", t_ops_compare)]:
        check(name, fn)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
