"""收據：腳本另外寫一份給程式讀的結構化結果；給模型的文字照舊印在標準輸出，一個字都不變。

harness 執行腳本時用環境變數 AGENT_RECEIPT_PATH 指定收據寫到哪個檔案（agent_core/dispatch.py 的 _exec_script）；沒有設定就不寫，
直接在終端機跑腳本跟以前一樣。腳本的 execute(argv) 回傳給模型的文字，另外：
- 錯誤的出口：`return fail(text, "args")`（text 是 _path_common.resolve 這類共用層回的 ToolError 時，種類可以省略）；
- 成功的出口：`result("pass" 或 "empty", counts={...}, items=[...], truncated=..., 其他欄位)`，再回傳文字；
- 進入點：`main(execute, "<技能名稱>")`。

欄位（每個工具的 counts、items 與其他欄位寫在工具規格的 `receipt`，evals/skills 核對規格跟腳本寫的一致）：
- status：pass（有結果）、empty（成功，但結果是空的：0 筆、空目錄、空檔案）、error；
- error_kind（error 時）：
  - args：這一次的輸入不對（參數、選項、路徑、檔案的種類或格式不合這個工具）——換參數或換工具修得好；
  - env：環境擋住（沒有權限、找不到指令、裝置讀不到）——換參數修不好；
  - timeout：逾時，而且沒有任何結果（有部分結果時是 pass，truncated 為真）；
  - parse：腳本自己出錯（未預期的例外、沒有記收據）——要修程式；
- near（error 時，有才記）：找不到路徑時的相近路徑（_path_common.near_paths 的候選；低階執行器的第 1 級照它判斷：好幾個時不替上一層選）；
- counts：程式算好的數量；items：項目清單（路徑、行號、名稱…），最多 ITEMS_MAX 筆；truncated：結果或清單不完整；
- tool、version、cwd，與各工具自己的欄位。
"""
import json
import os
import sys

ENV = "AGENT_RECEIPT_PATH"
VERSION = 1
ERROR_KINDS = ("args", "env", "timeout", "parse")
ITEMS_MAX = 1000

_state = {}


class ToolError(str):
    """[ERROR] 的文字（照舊給模型）加上錯誤的種類與相近的路徑（給收據）。它就是 str：凍結的工具拿共用層的錯誤當字串用，照舊
    （接上別的字就變回一般的 str，種類照呼叫 fail 時給的，相近的路徑不記）。"""

    def __new__(cls, text, kind, near=None):
        assert kind in ERROR_KINDS, kind
        obj = super().__new__(cls, text)
        obj.kind = kind
        obj.near = list(near or [])
        return obj


def _near(text):
    near = getattr(text, "near", None)
    return {"near": list(near)} if near else {}


def fail(text, kind=None):
    """記下 error 的收據，回傳原本的文字（呼叫端照舊 return 它）。kind 省略時用 ToolError 帶的種類。"""
    kind = kind or getattr(text, "kind", None)
    assert kind in ERROR_KINDS, (kind, str(text)[:120])
    _state.clear()
    _state.update(status="error", error_kind=kind, **_near(text))
    return ToolError(text, kind, getattr(text, "near", None))


def result(status, counts=None, items=None, truncated=False, **fields):
    """記下 pass／empty 的收據。items 超過 ITEMS_MAX 筆只留前面的，truncated 跟著設成真。"""
    assert status in ("pass", "empty"), status
    items = list(items or [])
    _state.clear()
    _state.update(status=status, error_kind=None, counts=dict(counts or {}), items=items[:ITEMS_MAX],
                  truncated=bool(truncated) or len(items) > ITEMS_MAX, **fields)


def _final(text):
    """這一次要寫的收據：腳本記的；沒記、或記的跟回傳的文字對不上（回 [ERROR] 卻記成 pass）時，當成腳本的錯（parse）。"""
    is_error = str(text).lstrip().startswith("[ERROR]")
    if _state and (_state["status"] == "error") == is_error:
        return dict(_state)
    if is_error and isinstance(text, ToolError):
        return {"status": "error", "error_kind": text.kind, **_near(text)}
    return {"status": "error", "error_kind": "parse", "note": "腳本沒有記收據，或記的跟回傳的文字對不上"}


def write(tool, data):
    path = (os.environ.get(ENV) or "").strip()
    if not path:
        return
    data = {"version": VERSION, "tool": tool, "cwd": os.getcwd(), **data}
    try:
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        pass                                  # 收據寫不出來不影響給模型的文字（harness 讀不到就當沒有收據）


def main(execute, tool):
    """腳本的進入點：印 execute 回傳的文字（給模型），把收據寫到 AGENT_RECEIPT_PATH。
    未預期的例外跟以前一樣：[ERROR] 印到 stderr、exit code 1；收據記成 parse。"""
    _state.clear()
    try:
        text = execute(sys.argv[1:])
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] {tool} 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        write(tool, {"status": "error", "error_kind": "parse", "note": f"{type(e).__name__}: {e}"})
        sys.exit(1)
    write(tool, _final(text))         # 先寫收據：印的時候管道被關掉（終端機接 head）也不會少了收據
    try:
        print(text)
    except BrokenPipeError:
        sys.exit(1)
