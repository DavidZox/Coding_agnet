"""模型能力：Ollama /api/show 回報的 capabilities（completion、tools、thinking、vision、insert…）。

用途：thinking 開關只對支援的模型送 think=True（不支援時 Ollama 回 400「does not support thinking」）；設定畫面只在模型支援時
顯示開關。查詢結果依模型名稱快取（同一個名稱重新下載成別的版本時，重開程式才會更新）；Ollama 連不到時當作沒有、也不快取。
"""
import threading

_cache = {}
_lock = threading.Lock()


def capabilities(model):
    """模型的能力集合；查不到回空集合。"""
    if not model:
        return set()
    with _lock:
        if model in _cache:
            return _cache[model]
    try:
        import ollama
        res = ollama.show(model)
        caps = res.get("capabilities") if hasattr(res, "get") else getattr(res, "capabilities", None)
        caps = set(caps or [])
    except Exception:   # noqa: BLE001  Ollama 沒開、模型不存在：當作沒有，下次再查
        return set()
    with _lock:
        _cache[model] = caps
    return caps


def supports_thinking(model):
    return "thinking" in capabilities(model)


def think_arg(model, want):
    """要送給 Ollama 的 think 參數：想開而且模型支援才是 True；其他一律 False（不支援 thinking 的模型送 False 不會出錯）。"""
    return bool(want) and supports_thinking(model)


def thinking_text(response):
    """回應裡模型的思考內容（message.thinking）；沒有就回空字串。"""
    try:
        msg = response["message"]
    except (KeyError, TypeError):
        msg = getattr(response, "message", None)
    if msg is None:
        return ""
    try:
        t = msg["thinking"]
    except (KeyError, TypeError):
        t = getattr(msg, "thinking", None)
    return (t or "").strip()
