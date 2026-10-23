"""modify_memory：把使用者明確要求記住的經驗寫進長期記憶（prompts/Memory.md）。

Memory.md 每一輪都會透過 SkillAgent.load_long_term_memory() 進入 system prompt 的「Long Term Memory」區塊，
所以寫在這裡的是通用原則、選技能的規則、溝通風格、專案經驗——之後每一次對話都看得到。

用法：
    modify_memory_cmd.py "問題種類 | 問題描述 | 解決方法或結論"
回傳：成功以 [PASS] 開頭、失敗以 [ERROR] 開頭（專案共同慣例）。純本機檔案讀寫，不需要逾時機制。

一條最多 300 字：記憶整份載入、總共只載入 AGENT_MEMORY_MAX_CHARS（4000 字），超過時丟最舊的條目——以前沒有上限，
一條 5000 字的記憶會把其他所有記憶擠出 system prompt。
內容取自 action.args 的原文（HARNESS_RAW_ARGS，保留引號與空白）；內容中間有 --filter 這種字沒關係，只有整個參數就是一個
選項（舊的 --skill）時才拒絕。

檔案路徑一律由腳本自身位置推算：腳本執行時的 cwd 是 AI 的虛擬工作目錄（可被 change_dir 改變），
與 harness 安裝位置無關，不可用相對路徑。HARNESS_MEMORY_FILE 只給測試用（evals/skills 不碰正式的 Memory.md）。
"""
import os
import re
import shlex
import sys
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPTS_DIR))
MEMORY_FILE = (os.environ.get("HARNESS_MEMORY_FILE") or "").strip() or os.path.join(_PROJECT_ROOT, "prompts", "Memory.md")
MAX_CHARS = 300
USAGE = "用法: scripts/modify_memory_cmd.py \"問題種類 | 問題描述 | 解決方法或結論\"（整條用引號包住；沒有任何選項）"

# 記憶條目：「[MM-DD HH:MM] 內容」
_ENTRY_RE = re.compile(r"^\[\d{2}-\d{2} \d{2}:\d{2}\]\s*(.*)$")


def existing_entries(path):
    """讀出檔案中所有記憶條目的內容（去掉時間戳），用來判斷重複。"""
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = _ENTRY_RE.match(line.strip())
            if m and m.group(1).strip():
                entries.append(m.group(1).strip())
    return entries


def content_from(argv, raw):
    """記憶內容：原文跟拆好的參數一致時用原文（保留引號），否則用參數接起來。"""
    raw = (raw or "").strip()
    if raw:
        try:
            same = [a for a in shlex.split(raw) if a != ""] == list(argv)
        except ValueError:
            same = False
        if same:
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'" and len(argv) == 1:
                raw = raw[1:-1].replace("\\" + raw[0], raw[0])
            return raw
    return " ".join(argv)


def execute(memory_content):
    try:
        if not memory_content or not memory_content.strip():
            return f"[ERROR] 記憶內容不可為空。下一步：照格式給一條記憶。\n{USAGE}"
        content = " ".join(memory_content.split())  # 壓成單行，避免多行內容破壞條目格式
        if len(content) > MAX_CHARS:
            return (f"[ERROR] 記憶內容 {len(content)} 字，超過上限 {MAX_CHARS} 字：每一條記憶都會放進之後每一輪的 system prompt，"
                    f"太長會把較舊的記憶擠掉。下一步：精簡成一句「問題種類 | 描述 | 結論」再寫；細節寫成檔案（file_ops write），"
                    f"記憶裡只寫檔案路徑與結論。")
        if content in existing_entries(MEMORY_FILE):
            return "[PASS] 相同內容已存在於長期記憶，未重複寫入。"
        now = datetime.now().strftime("%m-%d %H:%M")
        if not os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                f.write("# Long Term Memory\n\n")
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{now}] {content}\n")
        n = len(existing_entries(MEMORY_FILE))
        return f"[PASS] 成功寫入長期記憶（每輪常駐 system prompt；{len(content)} 字，目前共 {n} 條）\nMemory: [{now}] {content}"
    except OSError as e:
        return f"[ERROR] 記憶寫入失敗：{e}。下一步：把這個錯誤告訴使用者（Memory.md 的權限或磁碟問題）。"


if __name__ == "__main__":
    try:
        argv = [a for a in sys.argv[1:] if a != ""]
        # 只有一種寫入目標：整個參數就是一個選項（例如舊的 --skill）時明確拒絕，不要把選項當成記憶內容寫進去
        if argv and argv[0].startswith("--") and not any(c.isspace() for c in argv[0]):
            print(f"[ERROR] modify_memory 沒有任何選項（收到 {argv[0]}）：記憶一律寫入 Memory.md。下一步：只給記憶內容重新執行；"
                  f"內容裡有 -- 開頭的字（例如 --filter）時，把整條記憶用引號包起來。\n{USAGE}")
            sys.exit(0)
        print(execute(content_from(argv, os.environ.get("HARNESS_RAW_ARGS"))))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] modify_memory 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
