"""評測的完整性（離線、幾秒）：模型會讀的文字裡不能有評測世界獨有的名稱。

範例用了評測情境的檔案、名稱、數值時，評測量到的是「會不會抄範例」而不是會不會做（2026-10-24 查 fs_edit_param 時發現：
file_ops 的範例正好是那一題的答案；設計筆記 2.19）。這裡把評測世界的名稱從評測的來源自動取出來（新增情境不用改這裡），
掃模型會讀的文字：

- prompts/ 底下的 .md（prompts/Memory.md 除外：那是使用者的長期記憶，會隨使用改變）、skills_system/SKILLS.md、
  skills_system/tools/*.md、skills_system/workflows/*.md；
- agent_core/、vision/、web_app/、skills_system/scripts/ 裡回給模型的字串（用法、[ERROR] 的例子）：程式裡的字串常數，docstring 與
  註解不算；scripts/mock_server.py（開發用的替身，本來就是評測沙盒）不算。

另外檢查 prompts/ 的範本跟程式對得上（2026-10-25 把程式裡給模型的字搬進 prompts/ 之後，設計筆記 2.22）：程式用到的每一則（prompt_files.load
或模組裡的 _t、_x… 這種取一則的小函式）都在、程式填的每個名稱範本裡都有 {名稱}、範本裡沒有沒人用的一則；讀範本的 agent_core/prompt_files.py
本身（取一則、一次填完、讀不到回空字串）。

評測世界的名稱：機器人（tb1…）、工作包（WP_…）、站點（a0…）與語意名稱（組裝線區-2…）、容器、映像、檔案沙盒的路徑、
設定檔裡的設定名稱、錯誤碼、數據的編號（exp_…）。調度系統本身的協定名稱（distribute、handshake_states、threshold_recovery_sec…）
是技能要描述的領域知識，評測沙盒照真的系統做，所以不算（ALLOWED）。範例要用 `<檔案>`、`<名稱>` 或評測世界沒有的名稱
（amr_07、p0、WP_0815、cam_driver、config/camera.yaml…）。

    python3 evals/integrity/selftest.py
"""
import ast
import glob
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
           "evals/chat/scenarios.py", "evals/workflow/sandbox.py"]
# 調度系統與 ROS 2 本身的名稱：評測沙盒照真的系統做，技能規格要描述它們
# （/opt/ros 是 ROS 2 的安裝位置：容器裡的 ros2 指令要先 source 它）
ALLOWED = {"ros__parameters", "authorize_timeout_sec", "threshold_recovery_sec", "threshold_ovp_sec", "fleet_name",
           "web_console_url", "manual_trigger_url", "/opt/ros"}
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
    return names


def _pattern(names):
    alts = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(n) for n in alts) + r")(?![\w-])")


def facing_docs():
    docs = glob.glob(os.path.join(PROJECT, "prompts", "**", "*.md"), recursive=True)
    docs = [p for p in docs if os.path.basename(p) != "Memory.md"]
    docs += [os.path.join(PROJECT, "skills_system", "SKILLS.md")]
    docs += glob.glob(os.path.join(PROJECT, "skills_system", "tools", "*.md"))
    docs += glob.glob(os.path.join(PROJECT, "skills_system", "workflows", "*.md"))
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
    加上段名；路徑、段名可以是字串、模組常數或 a if … else b。整份檔案用 f-string 組路徑的（orchestra/{name}）不算看不懂。"""
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
                        inside.add(id(c))          # 整份檔案、路徑用 f-string 組的小函式（_read("planner.md")）
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
        for kind in ("機器人", "工作包", "數據", "錯誤碼", "站點", "站點的語意名稱", "檔案", "容器", "映像", "設定名稱"):
            assert kind in kinds, f"沒有取到「{kind}」：{sorted(kinds)}"
        for x in ("tb4", "WP_L2", "exp_20261014_084506", "E1203", "a7", "組裝線區-2", "configs/robots.yaml",
                  "configs/nav/nav_params.yaml", "/etc/web_cache.conf", "ops_notes/2026-10-10.md", "web_cache", "talker_box",
                  "scratch_box", "ros2_humble", "ubuntu:24.04", "max_vel_x", "battery_low"):
            assert x in names, f"沒有取到 {x}"
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
        assert len(uses) > 200, f"只找到 {len(uses)} 處用到範本：檢查的寫法跟程式對不上了"
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
                     ("prompts、SKILLS.md、技能規格、工作流沒有評測世界的名稱", t_docs),
                     ("agent_core、vision、web_app 與技能腳本回給模型的字串沒有評測世界的名稱", t_code),
                     ("prompts/ 的範本跟程式對得上：用到的每一則都在、填的名稱範本裡都有、沒有沒人用的一則", t_templates),
                     ("讀範本（agent_core/prompt_files.py）：取一則、一次填完、讀不到回空字串、檔案改了就重讀", t_loader)]:
        check(name, fn)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
