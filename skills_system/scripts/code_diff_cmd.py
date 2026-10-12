"""code_diff：看程式改了什麼——coding job 開始以來的變更（跟 job 開始前的備份比），或 git 工作區的變更。

- coding job 中（有 CODE_BACKUP_DIR）：預設看這個 job 改過的所有檔案；給檔名只看那一個。
- 主對話：--job <編號|latest> 看某個 coding job 的變更（讀 logs/coding_jobs/<編號>/）；都沒有時退回 git diff。
- --stat：只列每個檔案加減幾行。新增與刪除的檔案也會列出。
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JOBS_DIR = os.path.join(_PROJECT_ROOT, "logs", "coding_jobs")
MAX_OUTPUT_CHARS = 12000
USAGE = "用法: scripts/code_diff_cmd.py [檔案] [--stat] [--job <編號|latest>]"


def parse_args(argv):
    opts = {"file": None, "stat": False, "job": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--stat":
            opts["stat"] = True
        elif a == "--job":
            if i + 1 >= len(argv):
                return None, f"[ERROR] --job 後面需要編號（或 latest）。\n{USAGE}"
            opts["job"] = argv[i + 1].lstrip("#")
            i += 1
        elif a.startswith("--"):
            return None, f"[ERROR] 不認識的選項 {a}。\n{USAGE}"
        else:
            opts["file"] = a
        i += 1
    return opts, None


def job_dir(ref):
    if not os.path.isdir(JOBS_DIR):
        return None
    jobs = sorted(d for d in os.listdir(JOBS_DIR) if d.isdigit())
    if not jobs:
        return None
    if ref in ("latest", "last", ""):
        return os.path.join(JOBS_DIR, jobs[-1])
    if ref.isdigit():
        name = f"{int(ref):03d}"
        return os.path.join(JOBS_DIR, name) if name in jobs else None
    return None


def backup_diffs(bdir, workspace, only=None):
    """[(相對路徑, 狀態, diff, +, −)]：狀態＝修改／新增／刪除。"""
    out = []
    for rel, entry in sorted(cc.load_manifest(bdir).items()):
        if only and os.path.normpath(only) != os.path.normpath(rel):
            continue
        cur_path = os.path.join(workspace, rel)
        old = cc.original_text(rel, bdir)
        old = "" if old is None else old
        exists = os.path.exists(cur_path)
        new = cc.read_text(cur_path) if exists else ""
        if not entry.get("existed") and not exists:
            continue
        status = "新增" if not entry.get("existed") else ("刪除" if not exists else "修改")
        diff, a, d = cc.unified_diff(old, new, rel)
        if diff or status != "修改":
            out.append((rel, status, diff, a, d))
    return out


def render(title, items, stat):
    if not items:
        return f"[PASS] {title}：沒有任何變更。"
    total_a = sum(x[3] for x in items)
    total_d = sum(x[4] for x in items)
    lines = [f"[PASS] {title}：{len(items)} 個檔案（+{total_a} −{total_d}）"]
    lines += [f"  {rel}（{status}，+{a} −{d}）" for rel, status, _, a, d in items]
    if not stat:
        body = "\n\n".join(diff for _, _, diff, _, _ in items if diff)
        lines.append("")
        lines.append(cc.clip_middle(body, MAX_OUTPUT_CHARS, "diff"))
    return "\n".join(lines)


def main(argv):
    opts, err = parse_args(argv)
    if err:
        return err
    if opts["job"] is not None:
        d = job_dir(opts["job"])
        if not d:
            return f"[ERROR] 找不到 coding job #{opts['job']}（logs/coding_jobs/ 底下沒有）。用 code_job_status 看有哪些 job。"
        try:
            with open(os.path.join(d, "state.json"), encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            return f"[ERROR] coding job #{opts['job']} 的狀態檔讀不到。"
        items = backup_diffs(os.path.join(d, "backup"), state.get("workspace", ""), opts["file"])
        return render(f"coding job #{state.get('id', opts['job'])} 的變更（工作區 {state.get('workspace')}）", items, opts["stat"])
    bdir = cc.backup_dir()
    if bdir:
        items = backup_diffs(bdir, cc.base_root(), opts["file"])
        return render("這個 coding job 到目前為止的變更", items, opts["stat"])
    root = cc.base_root()
    try:
        cmd = ["git", "--no-optional-locks", "-C", root, "diff"] + (["--stat"] if opts["stat"] else []) + (["--", opts["file"]] if opts["file"] else [])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return f"[ERROR] 執行 git diff 失敗：{e}"
    if r.returncode != 0:
        return (f"[ERROR] {root} 不是 git 專案、也不在 coding job 裡，沒有比較的基準。"
                f"要看某個 coding job 的變更請加 --job <編號>。\n{r.stderr.strip()}")
    out = r.stdout.strip()
    if not out:
        return f"[PASS] git 工作區沒有未提交的變更（{root}）。"
    return f"[PASS] git 工作區的變更（{root}，尚未提交）：\n{cc.clip_middle(out, MAX_OUTPUT_CHARS, 'diff')}"


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_diff 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
