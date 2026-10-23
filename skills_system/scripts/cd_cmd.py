"""change_dir：切換 harness 的工作目錄（之後的本機技能都在這裡執行、相對路徑相對於這裡）。

成功時輸出末行 `[CWD_CHANGED] <絕對路徑>`，harness 據此更新 current_cwd（只認輸出最後的標記行）。
切換前檢查：存在、是目錄、目前使用者能讀取並進入（`cd /root` 以前回 [PASS]，之後每個腳本都在一個進不去的目錄執行而失敗）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402

USAGE = ("用法: scripts/cd_cmd.py <目錄>\n"
         "  目錄：絕對路徑、相對於目前工作目錄的路徑、或 ~ 開頭；不給就切到家目錄。")


def execute(argv):
    args = [a for a in argv if a != ""]
    if args and args[0].lower() == "cd" and len(args) > 1:     # 模型把指令名稱也寫進參數：cd /opt
        args = args[1:]
    options = [a for a in args if a.startswith("-") and a != "-"]
    if options:
        return f"[ERROR] change_dir 沒有選項（收到 {'、'.join(options)}）。下一步：只給目錄路徑。\n{USAGE}"
    if len(args) > 1:
        joined = pc.join_if_exists(args)
        if joined is None:
            return (f"[ERROR] 一次只能切換到一個目錄（收到 {len(args)} 個參數：{'、'.join(args)}）。"
                    f"下一步：只給一個路徑；路徑含空白請用引號包住。\n{USAGE}")
        args = [joined]
    target = args[0] if args else "~"
    if target == "-":
        return "[ERROR] change_dir 不支援 cd -（不記得上一個目錄）。下一步：直接給要切換到的目錄路徑。"
    abs_path, err = pc.resolve(target, "dir", file_hint=f"要切換到它所在的目錄請用 {pc.display(os.path.dirname(os.path.abspath(pc.expand(target))))}")
    if err:
        if err.startswith("[ERROR] 沒有權限"):
            err = err.replace("[ERROR] 沒有權限讀取目錄", "[ERROR] 沒有權限進入目錄", 1) + "；工作目錄沒有改變"
        return err
    try:
        n = len(os.listdir(abs_path))
    except OSError:
        n = None
    what = f"（裡面有 {n} 項）" if n is not None else ""
    return f"[PASS] 已切換工作目錄: {abs_path}{what}\n[CWD_CHANGED] {abs_path}"


if __name__ == "__main__":
    try:
        print(execute(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] change_dir 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
