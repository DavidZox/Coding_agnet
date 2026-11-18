"""真實專案評測的快照：amr_base 固定在一個 commit，從 git 取出三個套件存成 tar（放在專案外），評測時解開成唯讀。

    python3 evals/repo/snapshot.py build     # 從 ~/fih_humanoid_amr 的 git 取出（那個 commit 要還在），寫出 tar、印出雜湊
    python3 evals/repo/snapshot.py check     # tar 在不在、雜湊對不對

固定版本的理由：答案由程式從這份快照算（evals/repo/questions.py），程式之後改了，題目的答案也不會跟著變。
tar 不進版控（約 160 MB，含 PDF 與圖）。雜湊對的是檔名與內容（不是 tar 本身的位元組），換一版 git 重建也對得上；內容變了就對不上。
"""
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tarfile

REPO = os.path.expanduser("~/fih_humanoid_amr")
COMMIT = "6d91797a686b8e34a1254ab261bd6a8f7c7c82dd"   # 2026-11-18 的 HEAD
PATHS = ["amr_base/src/amr_base_sw", "amr_base/src/amr_base_hw", "amr_base/src/fih_rmf_system"]
TAR = os.path.expanduser(f"~/cah_eval/repo_snapshots/amr_base_{COMMIT[:8]}.tar")
DIGEST = "f6411a65de77141017b286e8db2033b0d4512a63e6eacc4a96d306e23db6947f"
SRC = "amr_base/src"   # 解開後題目的工作目錄：三個套件在這底下


def digest(path):
    """tar 裡每個成員的檔名、種類與內容（照檔名排序）的 sha256。"""
    h = hashlib.sha256()
    with tarfile.open(path) as t:
        members = sorted((m for m in t.getmembers() if m.isfile() or m.isdir() or m.issym()), key=lambda m: m.name)
        for m in members:
            h.update(f"{m.name}\0{m.type.decode()}\0{m.linkname}\0".encode())
            if m.isfile():
                with t.extractfile(m) as f:
                    for block in iter(lambda: f.read(1 << 20), b""):
                        h.update(block)
    return h.hexdigest()


def build():
    os.makedirs(os.path.dirname(TAR), exist_ok=True)
    tmp = TAR + ".part"
    with open(tmp, "wb") as f:
        subprocess.run(["git", "-C", REPO, "archive", "--format=tar", COMMIT, *PATHS], stdout=f, check=True)
    os.replace(tmp, TAR)
    return digest(TAR)


def problem():
    """快照不能用的原因；能用回 None。"""
    if not os.path.exists(TAR):
        return f"沒有快照 {TAR}（python3 evals/repo/snapshot.py build）"
    got = digest(TAR)
    if got != DIGEST:
        return f"快照的內容跟固定的版本不一樣：{got}（應該是 {DIGEST}）"
    return None


def extract(dest):
    """解開到 dest，全部改成唯讀；回傳題目的工作目錄。"""
    err = problem()
    if err:
        raise RuntimeError(err)
    def keep_inside(member, path):
        # 指到快照外面的連結不解開（例如 amr_base_sw/tool/recordings → 容器裡的 /workspaces/…，主機上本來就不存在）：
        # 留著的話，agent 跟著連結就讀到快照外面的東西
        if member.issym() or member.islnk():
            target = os.path.normpath(os.path.join(os.path.dirname(member.name), member.linkname))
            if os.path.isabs(member.linkname) or target.startswith(".."):
                return None
        return tarfile.data_filter(member, path)

    with tarfile.open(TAR) as t:
        t.extractall(dest, filter=keep_inside)
    for dp, dns, fns in os.walk(dest):
        for n in fns + dns:
            p = os.path.join(dp, n)
            if not os.path.islink(p):
                os.chmod(p, os.stat(p).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return os.path.join(dest, SRC)


def remove(dest):
    for dp, dns, _ in os.walk(dest):
        for n in dns:
            p = os.path.join(dp, n)
            if not os.path.islink(p):
                os.chmod(p, os.stat(p).st_mode | stat.S_IWUSR)
    os.chmod(dest, os.stat(dest).st_mode | stat.S_IWUSR)
    shutil.rmtree(dest, ignore_errors=True)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "build":
        print(f"{TAR}\n內容的雜湊 {build()}")
    elif cmd == "check":
        err = problem()
        print(err or f"[PASS] {TAR}（{COMMIT[:8]}）")
        sys.exit(1 if err else 0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
