"""技能腳本的離線自我測試：每個技能直接執行腳本（不經過模型），檢查 [PASS] 與每一種 [ERROR] 的寫法（第一行、原因與下一步、截斷的說明）、
輸出的結構、可以自己用（不讀標準輸入、有逾時）。規範見 doc/技能撰寫規範.md。

    python3 evals/skills/selftest.py            # 全部
    python3 evals/skills/selftest.py fs docker  # 只跑某幾組（檔名 <組>_test.py）

每一組一個檔案 evals/skills/<組>_test.py，裡面的 t_* 函式各是一個情境（docstring 第一行是名稱）。需要容器或沙盒的情境自己判斷環境，
沒有就丟 Skip（印出略過的原因，不算失敗）。每個情境在臨時目錄跑，不碰正式的 logs/ 與使用者的檔案。"""
import importlib.util
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(PROJECT, "skills_system", "scripts")


class Skip(Exception):
    """這個情境需要的環境（容器、沙盒、套件）不在：略過、印出原因。"""


def run_script(name, *args, cwd=None, env=None, timeout=120, stdin_text=None):
    """直接執行 skills_system/scripts/<name>（跟 harness 的 _exec_script 一樣：sys.executable、cwd、環境變數），回傳 (exit code, 輸出文字)。
    輸出跟 harness 一樣：成功取 stdout；失敗取 stderr，沒有就 stdout。"""
    import subprocess
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, name), *args], capture_output=True, text=True, cwd=cwd or PROJECT, env=e,
                       timeout=timeout, input=stdin_text if stdin_text is not None else None,
                       stdin=None if stdin_text is not None else subprocess.DEVNULL)
    out = r.stdout.strip() if r.returncode == 0 else (r.stderr.strip() or r.stdout.strip())
    return r.returncode, out


def first_line(text):
    return (text or "").splitlines()[0] if text else ""


def assert_error(text, *words):
    """[ERROR] 開頭，而且有寫下一步（含 words 裡的每一個字）。"""
    assert text.startswith("[ERROR]"), f"應該是 [ERROR]：{text[:300]}"
    for w in words:
        assert w in text, f"[ERROR] 應該提到「{w}」：{text[:500]}"


def load_groups(names=None):
    groups = []
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith("_test.py"):
            continue
        group = fn[:-len("_test.py")]
        if names and group not in names:
            continue
        spec = importlib.util.spec_from_file_location(f"skills_{group}_test", os.path.join(HERE, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tests = [(n, getattr(mod, n)) for n in sorted(dir(mod)) if n.startswith("t_") and callable(getattr(mod, n))]
        tests.sort(key=lambda t: t[1].__code__.co_firstlineno)
        groups.append((group, tests))
    return groups


def main(argv):
    sys.path.insert(0, HERE)
    import selftest as module   # 測試檔 `from selftest import Skip` 拿到的是模組裡的 Skip，跟直接執行時的 __main__.Skip 不是同一個類別
    skip_types = (Skip, module.Skip)
    results, skipped = [], []
    for group, tests in load_groups(set(argv) or None):
        for name, fn in tests:
            title = f"[{group}] " + ((fn.__doc__ or name).strip().splitlines()[0])
            try:
                fn()
                results.append((title, True, ""))
                print(f"✅ {title}")
            except skip_types as e:
                skipped.append((title, str(e)))
                print(f"⏭️  {title}（略過：{e}）")
            except Exception:   # noqa: BLE001
                results.append((title, False, traceback.format_exc()))
                print(f"❌ {title}")
    failed = [r for r in results if not r[1]]
    for title, _, tb in failed:
        print(f"\n---- {title} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過" + (f"，{len(skipped)} 個略過" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
