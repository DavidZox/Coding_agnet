"""準備 DevBench 評測：下載固定版本的資料（逐檔驗證 git blob SHA-1）、建立跑 Python 測試的虛擬環境、檢查 C／C++ 工具鏈、
（--verify）用參考實作跑一次官方測試確認計分方式與環境都對。

    python3 evals/devbench/prepare.py                  # 下載＋建立 evals/devbench/.venv＋檢查工具鏈
    python3 evals/devbench/prepare.py --verify         # 另外用參考實作跑官方測試（應該全部通過）
    python3 evals/devbench/prepare.py --from-dir <DevEval 的 benchmark_data 目錄>   # 不連網路：從本機複製（一樣逐檔驗證）
    python3 evals/devbench/prepare.py --only readtime,area_calculation

資料放在 evals/devbench/data/<語言>/<repo>/（約 7 MB），虛擬環境在 evals/devbench/.venv（pandas、matplotlib 等，約 300 MB）；
兩個都在 .gitignore。不需要 sudo；缺 g++、gtest、sqlite3 時會印出安裝方式。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from evals.devbench import evaluate as ev  # noqa: E402
from evals.devbench.repos import COMMIT, PYTHON_REQUIREMENTS, REPOS  # noqa: E402
from skills_system.scripts import _code_common as cc  # noqa: E402

API = "https://api.github.com/repos/open-compass/DevEval/git/trees/{sha}?recursive=1"
RAW = "https://raw.githubusercontent.com/open-compass/DevEval/{commit}/benchmark_data/{lang}/{repo}/{path}"


def _get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "coding-agent-harness-devbench"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fetch_repo(name, from_dir=None):
    """回傳 (下載或複製的檔案數, 已經存在而略過的檔案數)。內容的 SHA-1 跟固定版本不同就丟出例外。"""
    meta = REPOS[name]
    tree = json.loads(_get(API.format(sha=meta["tree"])))
    if tree.get("truncated"):
        raise RuntimeError(f"{name}：GitHub 回傳的檔案清單被截斷")
    blobs = [t for t in tree.get("tree", []) if t["type"] == "blob"]
    dst_root = ev.repo_dir(name)

    def one(t):
        dst = os.path.join(dst_root, t["path"])
        if os.path.isfile(dst):
            with open(dst, "rb") as f:
                if blob_sha(f.read()) == t["sha"]:
                    return "skip"
        if from_dir:
            with open(os.path.join(from_dir, meta["lang"], name, t["path"]), "rb") as f:
                data = f.read()
        else:
            data = _get(RAW.format(commit=COMMIT, lang=meta["lang"], repo=name, path=urllib.request.quote(t["path"])))
        if blob_sha(data) != t["sha"]:
            raise RuntimeError(f"{name}/{t['path']} 的內容跟固定版本不一樣（SHA-1 不符）")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        return "new"

    with ThreadPoolExecutor(max_workers=16) as ex:
        res = list(ex.map(one, blobs))
    return res.count("new"), res.count("skip")


def make_venv():
    py = ev.VENV_PY
    if not os.path.exists(py):
        print(f"🐍 建立虛擬環境 {ev.VENV} …", flush=True)
        subprocess.run([sys.executable, "-m", "venv", ev.VENV], check=True)
    check = "import pytest, bs4, pyquery, markdown2, lxml, pandas, numpy, matplotlib, progressbar"
    if subprocess.run([py, "-c", check], capture_output=True).returncode == 0:
        print("🐍 Python 測試需要的套件都在（pytest、pandas、lxml…）")
        return True
    print("🐍 安裝 Python 測試需要的套件（需要網路，幾分鐘）…", flush=True)
    r = subprocess.run([py, "-m", "pip", "install", "-q"] + PYTHON_REQUIREMENTS)
    ok = r.returncode == 0 and subprocess.run([py, "-c", check]).returncode == 0
    print("🐍 套件安裝" + ("完成" if ok else "失敗：請看上面 pip 的訊息"))
    return ok


def _try_compile(src, flags, env):
    d = tempfile.mkdtemp(prefix="devbench_tc_")
    try:
        path = os.path.join(d, "t.cpp")
        with open(path, "w") as f:
            f.write(src)
        r = subprocess.run(["g++", "-std=c++17", path, "-o", os.path.join(d, "t")] + flags, env=env, capture_output=True,
                           text=True, timeout=120)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout).strip()[-400:]
        r = subprocess.run([os.path.join(d, "t")], env=env, capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-400:]
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_toolchain():
    env = cc.toolchain_env(HERE)
    problems = []
    for tool in ("g++", "gcc", "make"):
        if not shutil.which(tool, path=env["PATH"]):
            problems.append(f"找不到 {tool}")
    if not problems:
        ok, msg = _try_compile("#include <gtest/gtest.h>\nTEST(A, B) { EXPECT_EQ(1, 1); }\n",
                               ["-lgtest", "-lgtest_main", "-pthread"], env)
        print("🧪 GoogleTest：" + ("OK" if ok else f"不能用（{msg}）"))
        if not ok:
            problems.append("GoogleTest")
        ok, msg = _try_compile("#include <sqlite3.h>\nint main() { return sqlite3_libversion_number() > 0 ? 0 : 1; }\n",
                               ["-lsqlite3"], env)
        print("🗄️ SQLite（people_management 需要）：" + ("OK" if ok else f"不能用（{msg}）"))
        if not ok:
            problems.append("SQLite")
    for p in problems:
        print(f"⚠️ {p}")
    if problems:
        print("可以這樣安裝（需要 sudo，請自己在終端機執行）：\n"
              "    sudo apt install -y build-essential libgtest-dev libsqlite3-dev\n"
              "不想用 sudo：從原始碼裝到 ~/.local（harness 的 code_test 預設會找 ~/.local，見 evals/devbench/README.md）。")
    return not problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只處理這些 repo（逗號分隔）")
    ap.add_argument("--from-dir", default=None, help="從本機的 DevEval benchmark_data 目錄複製，不從 GitHub 下載")
    ap.add_argument("--verify", action="store_true", help="用參考實作跑官方測試，確認環境與計分方式")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(REPOS)
    unknown = [n for n in names if n not in REPOS]
    if unknown:
        raise SystemExit(f"不認識的 repo：{'、'.join(unknown)}（可以用的：{'、'.join(REPOS)}）")
    if not args.skip_download:
        print(f"📥 DevBench（{COMMIT[:10]}）{len(names)} 個 repo → {ev.DATA}")
        for n in names:
            new, skip = fetch_repo(n, args.from_dir)
            print(f"  {n:30s} 新的 {new} 個檔案、已經有的 {skip} 個（SHA-1 都驗證過）", flush=True)
    venv_ok = make_venv()
    tc_ok = check_toolchain()
    if args.verify:
        print("🔁 用參考實作跑官方的單元測試與驗收測試（應該全部通過）：")
        results = ev.verify_reference(names)
        bad = [n for n, r in results if r["unit"] != r["unit_total"] or r["acceptance"] != r["acceptance_total"]]
        print("✅ 全部通過：環境與計分方式沒問題" if not bad else f"❌ 沒有全部通過：{'、'.join(bad)}")
        if bad:
            sys.exit(1)
    if not (venv_ok and tc_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
