"""image_inspect：對磁碟上的影像檔（截圖、相機快照）依提示詞做視覺模型分析，回傳文字（vision library 的 analyze）。

送給模型前等比縮小到長邊 1600 像素（相機原圖幾千像素時編碼、傳輸、推論都慢很多，文字也不會因此更清楚）。
路徑在主機上找不到、又是絕對路徑、而且有目標容器（TARGET_CONTAINER）時，當成容器內的路徑：依容器的 bind mount 換成主機路徑
（_ros2_data_common.container_mounts／to_host_path）；不在任何 mount 底下就說怎麼複製出來。像素多到 Pillow 拒絕開啟
（DecompressionBombError）時回明確的 [ERROR]。逾時 300 秒。
"""
import base64
import os
import sys

# 本腳本由 Agent 以 `python3 scripts/image_inspect_cmd.py` 從 AI 的工作目錄執行，
# 要把 harness 專案根目錄加進 sys.path 才 import 得到 vision library。
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, _PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import _path_common as pc  # noqa: E402

TIMEOUT_SECONDS = 300   # 視覺推論可能較慢；必須低於 Agent_Runner.TOOL_EXEC_TIMEOUT (600)
MAX_DIM = 1600          # 送給模型前長邊縮到這麼多像素
DEFAULT_PROMPT = "請詳細描述這張影像的內容，並逐字列出可見的文字、數值、狀態指示與任何異常之處。"
USAGE = (
    "用法: scripts/image_inspect_cmd.py <影像檔> [\"提示詞\"]\n"
    "  影像檔：相對於目前工作目錄或絕對路徑（可用 ~；目標容器裡的路徑會依 bind mount 換成主機路徑）；PNG／JPEG／WebP／BMP／GIF，上限 20MB。\n"
    "  提示詞：省略時用預設的描述提示詞（描述內容並逐字列出文字、數值、狀態）。"
)


def _locate(image_path):
    """→ (主機上的路徑, 說明, 錯誤)。"""
    abs_path = os.path.abspath(pc.expand(image_path))
    if os.path.exists(abs_path):
        return abs_path, "", None
    container = (os.environ.get("TARGET_CONTAINER") or "").strip()
    if container and image_path.startswith("/"):
        import _ros2_data_common as rdc
        mounts = rdc.container_mounts(container)
        host = rdc.to_host_path(image_path, mounts)
        if host and os.path.exists(host):
            return host, f"容器 {container} 的 {image_path} 對應到主機的 {host}", None
        base = os.path.basename(image_path) or "image.png"
        if host:
            return None, "", (f"[ERROR] 找不到影像檔：{image_path}（在容器 {container} 的 bind mount 底下，對應到主機的 {host}，但那裡沒有這個檔案）。"
                              f"下一步：用 docker_runcmd 在容器裡 ls 確認檔名，或用 find_file {base} {os.path.dirname(host)} 在主機上找。")
        return None, "", (f"[ERROR] 找不到影像檔：{image_path}——主機上沒有這個路徑；如果是容器 {container} 裡的檔案，它不在任何 bind mount 底下，"
                          f"主機讀不到。下一步：先用 docker_runcmd 確認檔案存在，再用 host_runcmd 複製出來"
                          f"（docker cp {container}:{image_path} /tmp/{base}，會請使用者確認），然後 image_inspect /tmp/{base}。")
    return None, "", pc.not_found(image_path, "file", "影像檔")


def _next_step(msg):
    if "無法連線" in msg or "ollama serve" in msg or "connect" in msg.lower():
        return "請使用者啟動 Ollama（ollama serve）；不要重試"
    if "模型不存在" in msg or "ollama pull" in msg:
        return "請使用者先下載視覺模型（訊息裡的 ollama pull 指令）；不要重試"
    if "逾時" in msg:
        return "改問更具體的問題（只問要看的那一部分），或請使用者先裁切出重點區域"
    if "不是可辨識的影像格式" in msg or "讀取" in msg:
        return "確認是影像檔（PNG／JPEG／WebP／BMP／GIF）；其他格式請使用者轉成 PNG"
    if "超過上限" in msg:
        return "請使用者先縮小或裁切影像（20MB 以內）"
    if "是目錄" in msg:
        return "給目錄裡的影像檔路徑（用 list_dir 或 find_file \"*.png\" 找）"
    return "修正路徑或提示詞再試；看不出原因就把錯誤告訴使用者"


def execute(image_path, prompt=""):
    image_path = (image_path or "").strip()
    prompt = (prompt or "").strip() or DEFAULT_PROMPT
    if not image_path:
        return f"[ERROR] 沒有給影像檔路徑。下一步：給影像檔的路徑（找檔案用 find_file \"*.png\"）。\n{USAGE}"
    try:
        from PIL import Image
        from vision import DEFAULT_MODEL, VisionError, analyze, from_file, to_data_url
    except ImportError as e:
        return (f"[ERROR] 缺少 Python 套件 {getattr(e, 'name', '') or e}，image_inspect 不能用。下一步：告訴使用者需要安裝："
                f"{sys.executable} -m pip install pillow ollama；不要自己安裝。")
    path, note, err = _locate(image_path)
    if err:
        return err
    try:
        img = from_file(path)
        w, h, url = to_data_url(img, max_dim=MAX_DIM)
        data = base64.b64decode(url.split(",", 1)[1])
        text = analyze([data], prompt, timeout=TIMEOUT_SECONDS)
    except Image.DecompressionBombError as e:
        return (f"[ERROR] 影像的像素太多，Pillow 拒絕開啟（防止解壓縮炸彈：{e}）。"
                f"下一步：請使用者先縮小或裁切影像（例如長邊 4000 像素以內）再分析；不要重試同一個檔案。")
    except VisionError as e:
        return f"[ERROR] {e}。下一步：{_next_step(str(e))}。"
    size = f"{img.width}x{img.height}" + (f"，送給模型前縮小成 {w}x{h}" if (w, h) != (img.width, img.height) else "")
    return (
        f"[PASS] 影像分析結果（{image_path}，{size}，模型 {DEFAULT_MODEL}）:\n"
        + (f"（{note}）\n" if note else "")
        + f"提示詞：{prompt}\n---\n{text}"
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            print(f"[ERROR] 參數不足：沒有給影像檔路徑。下一步：照下面的用法補上。\n{USAGE}")
            sys.exit(0)
        from _shell_common import protect_tail
        print(protect_tail(execute(sys.argv[1], " ".join(sys.argv[2:]))))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] image_inspect 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
