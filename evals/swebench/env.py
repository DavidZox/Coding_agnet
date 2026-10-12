"""SWE-bench 題目的開發環境：用題目的官方 Docker 映像，當作「這個專案已經裝好的開發環境」交給 harness（harness 本身不用改）。

做法：
1. 從映像起一個容器（--network none），主機上的工作區目錄掛在容器裡「同一個路徑」。映像裡已經裝好環境的 repo（/testbed）整份
   複製到工作區、/testbed 改成指向工作區的 symlink，site-packages 裡 editable install 的路徑（.pth、.egg-link、__editable__）
   也改成工作區 → 容器裡 import、建置、跑測試用的就是工作區裡的檔案。
2. 產生「包裝指令」目錄：python、pytest、make、cmake、gcc… 同名的小腳本，用 docker exec 在容器裡、同一個工作目錄執行同名指令
   （以主機使用者的 uid 執行，檔案的擁有者不會變成 root）。harness 的 code_test／code_run／code_check 會把 CODE_PYTHON 所在的
   目錄放在 PATH 最前面（_code_common.toolchain_env），所以 CODE_PYTHON=<包裝目錄>/python 時，harness 跑的測試、建置、編譯
   檢查都在題目的環境裡執行；讀寫檔案（code_view、code_edit）照常在主機上做——是同一份檔案。
3. 結束時：工作區相對於 base_commit 的改動（agent 新增的原始檔也算；建置產物、二進位檔、harness 的說明檔除外）就是 patch。

容器裡沒有的指令不做包裝（會用主機的）；C／C++ 專案的容器沒有 ninja 時，把 harness venv 裡的 ninja 複製進去（harness 的 code_test
看到 PATH 上有 ninja 就會用 -G Ninja）。容器裡沒有 Python 時，python／python3 指向主機的 Python（只用來跑輔助腳本）。
"""
import json
import os
import shlex
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "cah_eval", "swe")          # 工作區與包裝指令放這裡（不在 harness 專案裡）
UID = os.getuid()
GID = os.getgid()
INNER_TIMEOUT = 610     # 容器裡每個指令的上限（秒）：harness 的逾時只會結束 docker exec，容器裡的程序要自己停
CANDIDATES = ["python", "python3", "pytest", "py.test", "tox", "make", "cmake", "ctest", "ninja", "gcc", "g++", "cc", "c++",
              "clang", "clang++", "tclsh", "tclsh8.5", "tclsh8.6", "tclsh8.7", "autoreconf", "autoconf", "automake", "libtool",
              "pkg-config", "bison", "flex", "valgrind"]
SKIP_NEW = ("build/", "_build/", ".build/", "builds/", "CMakeFiles/", "cmake-build", "__pycache__/", ".pytest_cache/",
            ".tox/", ".eggs/", "node_modules/", ".mypy_cache/")
SKIP_NEW_EXT = (".o", ".a", ".so", ".dylib", ".pyc", ".pyo", ".d", ".gcda", ".gcno", ".gcov", ".log", ".tmp", ".exe")
RULES_FILE = ".coding_agent.md"       # harness 會讀工作區根目錄的這個檔案（coding_job.project_rules）


def sh(cmd, check=True, timeout=1800, **kw):
    """執行指令（list），回傳 stdout 文字；check=True 時失敗 raise（訊息含 stderr 的尾巴）。"""
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace", **kw)
    if check and res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:6])}… exit {res.returncode}：{(res.stderr or res.stdout)[-1500:]}")
    return res.stdout


def container_name(iid, tag):
    return f"cah_swe_{tag}_{iid}".lower().replace("/", "_")[:120]


def _host_ninja():
    """harness venv 裡 ninja 套件附的真正執行檔（venv/bin/ninja 是 Python 的進入點，不能複製）。"""
    try:
        import ninja  # noqa: F401
        d = os.path.join(os.path.dirname(ninja.__file__), "data", "bin", "ninja")
        return d if os.path.isfile(d) else None
    except ImportError:
        for p in (os.path.join(HOME, "aiagent_venv_env", ".venv", "lib"),):
            for dirpath, _, files in os.walk(p):
                if dirpath.endswith(os.path.join("ninja", "data", "bin")) and "ninja" in files:
                    return os.path.join(dirpath, "ninja")
    return None


def remove_container(name):
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)


def copy_testbed(image, dest):
    """映像裡的 /testbed（題目的 repo，base_commit、環境已經建好）複製到主機的 dest（擁有者是主機使用者）。"""
    os.makedirs(dest, exist_ok=True)
    sh(["docker", "run", "--rm", "--network", "none", "-v", f"{dest}:{dest}", image, "bash", "-c",
        f"cp -a /testbed/. {shlex.quote(dest)}/ && chown -R {UID}:{GID} {shlex.quote(dest)}"], timeout=1800)


def start(inst, ws, tag, bin_root=None):
    """起題目的容器、準備工作區與包裝指令。回傳 env 資訊（dict，可以 json）。ws 必須是不存在或空的目錄。"""
    name = container_name(inst["instance_id"], tag)
    remove_container(name)
    if os.path.isdir(ws):
        shutil.rmtree(ws)
    os.makedirs(ws)
    image = inst["image"]
    sh(["docker", "run", "-d", "--name", name, "--network", "none", "-v", f"{ws}:{ws}", image, "tail", "-f", "/dev/null"])
    q = shlex.quote(ws)
    setup = (f"set -e; cp -a /testbed/. {q}/; chown -R {UID}:{GID} {q}; rm -rf /testbed; ln -s {q} /testbed; "
             # editable install 指向 /testbed 的路徑改成工作區（-xdev：不掃掛進來的工作區）
             f"find / -xdev \\( -name '*.pth' -o -name '*.egg-link' -o -name '__editable__*' \\) -path '*-packages*' "
             f"-print0 2>/dev/null | xargs -0 -r grep -l /testbed 2>/dev/null | xargs -r sed -i 's#/testbed#{ws}#g' || true")
    sh(["docker", "exec", name, "bash", "-c", setup], timeout=1800)
    base_path = sh(["docker", "exec", name, "printenv", "PATH"]).strip() or "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    has_conda = subprocess.run(["docker", "exec", name, "test", "-x", "/opt/miniconda3/envs/testbed/bin/python"]).returncode == 0
    path = ("/opt/miniconda3/envs/testbed/bin:" if has_conda else "") + base_path
    probe = "; ".join(f"p=$(command -v {c}) && echo \"{c} $p\"" for c in CANDIDATES)
    found = {}
    for line in sh(["docker", "exec", "-e", f"PATH={path}", name, "bash", "-c", probe + "; true"]).splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            found[parts[0]] = parts[1]
    notes = []
    is_c = inst.get("lang") in ("C", "C++")
    if is_c and "ninja" not in found and os.path.isfile(os.path.join(ws, "CMakeLists.txt")):
        nj = _host_ninja()
        if nj:
            sh(["docker", "cp", nj, f"{name}:/usr/local/bin/ninja"])
            found["ninja"] = "/usr/local/bin/ninja"
            notes.append("容器沒有 ninja：複製了 harness venv 的 ninja 進去")
    pkg_roots = [d for d in (os.path.join(ws, "src"), os.path.join(ws, "lib"), ws)
                 if os.path.isdir(d) and (d == ws or any(os.path.isfile(os.path.join(d, x, "__init__.py")) for x in os.listdir(d)))]
    py_in_container = "python3" in found or "python" in found
    bindir = os.path.join(bin_root or os.path.join(ROOT, "env", tag), inst["instance_id"], "bin")
    if os.path.isdir(bindir):
        shutil.rmtree(bindir)
    os.makedirs(bindir)
    runner = os.path.join(bindir, "_in_container")
    envs = ["-e HOME=/tmp", "-e USER=agent", "-e LOGNAME=agent", "-e TERM=dumb", "-e LANG=C.UTF-8", "-e LC_ALL=C.UTF-8",
            "-e PYTHONDONTWRITEBYTECODE=1", f"-e PATH={shlex.quote(path)}"]
    if not is_c:
        envs.append(f"-e PYTHONPATH={shlex.quote(':'.join(pkg_roots))}")
    with open(runner, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n"
                f"# SWE-bench 評測用：在題目的容器（{name}）裡執行同名的指令；工作區在容器裡的路徑跟主機一樣。\n"
                'cwd="$PWD"\n'
                f'case "$cwd" in {q}|{q}/*) ;; *) cwd={q} ;; esac\n'
                f'exec docker exec -i -u {UID}:{GID} -w "$cwd" {" ".join(envs)} {name} '
                f'timeout -k 5 {INNER_TIMEOUT} "$(basename "$0")" "$@"\n')
    os.chmod(runner, 0o755)
    wrapped = []
    for cmd in CANDIDATES:
        if cmd in found:
            os.symlink("_in_container", os.path.join(bindir, cmd))
            wrapped.append(cmd)
    if not py_in_container:
        for cmd in ("python", "python3"):
            os.symlink(sys.executable, os.path.join(bindir, cmd))
        notes.append("容器沒有 Python：python／python3 用主機的（只用來跑輔助腳本）")
    elif "python" not in found:
        os.symlink("python3", os.path.join(bindir, "python"))
    # 工作區的 git：權限位元不算改動；harness 的說明檔不進 patch；記下開始時已經有的未追蹤檔案（不算 agent 的改動）
    sh(["git", "-C", ws, "config", "core.fileMode", "false"])
    with open(os.path.join(ws, ".git", "info", "exclude"), "a", encoding="utf-8") as f:
        f.write(f"\n{RULES_FILE}\n")
    untracked = sh(["git", "-C", ws, "ls-files", "--others", "--exclude-standard", "-z"]).split("\0")
    dirty = sh(["git", "-C", ws, "status", "--porcelain", "--untracked-files=no"]).strip()
    info = {"container": name, "image": image, "workspace": ws, "bindir": bindir, "code_python": os.path.join(bindir, "python"),
            "container_path": path, "pythonpath": pkg_roots if not is_c else [], "wrapped": wrapped, "found": found,
            "notes": notes, "pre_untracked": [u for u in untracked if u], "pre_dirty": dirty}
    with open(os.path.join(os.path.dirname(bindir), "env.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    return info


def write_rules(ws, text):
    with open(os.path.join(ws, RULES_FILE), "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def _skip_new(path):
    p = path.replace("\\", "/")
    return (any(("/" + s) in ("/" + p) for s in SKIP_NEW) or p.endswith(SKIP_NEW_EXT) or p.endswith(".egg-info")
            or "/.egg-info/" in p or ".egg-info/" in p or p == RULES_FILE)


def make_patch(ws, base_commit, pre_untracked=()):
    """工作區相對於 base_commit 的改動 → (patch 文字, 說明)。新增的檔案只算 agent 新寫的原始檔（開始時就有的未追蹤檔、
    建置產物、超過 1 MB 的檔案、二進位檔不算）。不改工作區的內容（最後把暫存區清回去）。"""
    git = ["git", "-C", ws, "-c", "core.fileMode=false"]
    notes = []
    pre = set(pre_untracked or ())
    new = [u for u in sh(git + ["ls-files", "--others", "--exclude-standard", "-z"]).split("\0") if u]
    add = []
    for rel in new:
        full = os.path.join(ws, rel)
        if rel in pre or _skip_new(rel):
            continue
        try:
            if os.path.getsize(full) > 1024 * 1024:
                notes.append(f"略過超過 1 MB 的新檔案 {rel}")
                continue
        except OSError:
            continue
        add.append(rel)
    sh(git + ["add", "-u"])
    for i in range(0, len(add), 200):
        sh(git + ["add", "--"] + add[i:i + 200])
    for line in sh(git + ["diff", "--cached", "--numstat", base_commit]).splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] == "-" and parts[1] == "-":
            sh(git + ["reset", "-q", "--", parts[2]], check=False)
            notes.append(f"略過二進位檔 {parts[2]}")
    patch = sh(git + ["diff", "--cached", base_commit])
    sh(git + ["reset", "-q"], check=False)
    return patch, notes


def stop(info, remove_workspace=True):
    remove_container(info["container"])
    if remove_workspace and os.path.isdir(info["workspace"]):
        shutil.rmtree(info["workspace"], ignore_errors=True)
