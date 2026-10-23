"""stt_engine：語音轉文字（faster-whisper）。兩種用法：
1. `--file 音檔`：辨識已經存在的音檔（wav、mp3、m4a、flac、ogg…；faster-whisper 自己解碼，不需要 ffmpeg）——不需要有人在旁邊，
   AI 可以自己用（心跳、常駐的工作）。
2. 不給 --file：用麥克風錄音後辨識，只在使用者要用說的時候用（需要有人對著麥克風說話）。錄音工具依環境選：WSL 用 Windows 端的
   ffmpeg.exe（路徑與麥克風 ID 在下面的設定區），Linux 用 arecord（ALSA 預設的錄音裝置）。

辨識在子程序裡跑（Whisper 的推論在 C++ 裡、本程序內沒辦法中斷），整段有逾時（預設 300 秒），逾時結束整個程序群組、
保留已經辨識出來的段落。缺套件時一開始就回 [ERROR]，寫明要請使用者執行的安裝指令。錄音檔與辨識結果寫在 harness 的
logs/stt/（以前寫進 AI 的工作目錄 stt_output.txt）。
"""
import datetime
import importlib.util
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _shell_common import run_shell  # noqa: E402

# ===== 環境設定（WSL + Windows 錄音裝置；換環境需修改這一區）=====
FFMPEG_PATH = "/mnt/c/ffmpeg/bin/ffmpeg.exe"
WSL_TEMP_DIR = "/mnt/c/temp"                          # WSL 端檢查／建立目錄用
WINDOWS_OUTPUT_PATH = r"C:\temp\input.wav"            # 交給 ffmpeg.exe 的 Windows 原生路徑（避開 WSL 權限問題）
MIC_DEVICE = r"@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\wave_{C0074AF2-0AB4-4BC4-BC79-5E04A3A91914}"
MODEL_PATH = os.environ.get("STT_MODEL", "small")
DEFAULT_RECORD_SECONDS, MAX_RECORD_SECONDS = 10, 60
DEFAULT_TIMEOUT, MAX_TIMEOUT = 300, 570
TEXT_SHOWN_CHARS = 6000
USAGE = ("用法: scripts/stt_engine_cmd.py [--file 音檔] [--lang 語言] [--record 秒數] [--timeout 秒數]\n"
         "  --file：辨識已經存在的音檔（wav、mp3、m4a、flac、ogg…），不需要有人在旁邊。\n"
         f"  不給 --file：用麥克風錄音（預設 {DEFAULT_RECORD_SECONDS} 秒，--record 改秒數，上限 {MAX_RECORD_SECONDS}），"
         "只在使用者要用說的時候用（要有人對著麥克風說話）。\n"
         f"  --lang：語言代碼（zh、en…；預設自動偵測）。--timeout：辨識的上限秒數（預設 {DEFAULT_TIMEOUT}、上限 {MAX_TIMEOUT}）。")


def parse_args(argv):
    o = {"file": None, "lang": None, "record": DEFAULT_RECORD_SECONDS, "timeout": DEFAULT_TIMEOUT}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--file", "--lang", "--record", "--timeout"):
            if i + 1 >= len(argv):
                return None, f"[ERROR] {a} 後面需要值。\n{USAGE}"
            v = argv[i + 1]
            if a in ("--record", "--timeout"):
                hi = MAX_RECORD_SECONDS if a == "--record" else MAX_TIMEOUT
                if not v.isdigit() or not 1 <= int(v) <= hi:
                    return None, f"[ERROR] {a} 要是 1～{hi} 的秒數，收到「{v}」。\n{USAGE}"
                v = int(v)
            o[a[2:]] = v
            i += 2
            continue
        if o["file"] is None and not a.startswith("-"):
            o["file"] = a                     # 直接給音檔路徑也可以
            i += 1
            continue
        return None, f"[ERROR] 不認識的參數「{a}」。下一步：照下面的用法改。\n{USAGE}"
    return o, None


def dependency_error():
    if importlib.util.find_spec("faster_whisper") is None:
        return (f"[ERROR] 缺少 Python 套件 faster-whisper（語音辨識要用），這台機器還不能做語音轉文字。下一步：告訴使用者需要安裝，"
                f"安裝指令：{sys.executable} -m pip install faster-whisper（第一次辨識會再下載 {MODEL_PATH} 模型，約幾百 MB）；"
                f"裝好之後再執行一次。不要自己安裝。")
    return None


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def record(seconds):
    """錄音 → (音檔路徑, 錯誤)。"""
    out_dir = pc.harness_logs_dir("stt")
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(FFMPEG_PATH):            # WSL：Windows 端 ffmpeg.exe 錄到 C:\temp，再從 /mnt/c 讀
        try:
            os.makedirs(WSL_TEMP_DIR, exist_ok=True)
        except OSError as e:
            return None, f"[ERROR] 無法建立錄音暫存目錄 {WSL_TEMP_DIR}：{e}。下一步：請使用者確認 C:\\temp 可以寫入。"
        cmd = [FFMPEG_PATH, "-f", "dshow", "-i", f"audio={MIC_DEVICE}", "-t", str(seconds), "-y", WINDOWS_OUTPUT_PATH]
        wav = os.path.join(WSL_TEMP_DIR, "input.wav")
        tool = "ffmpeg.exe"
    elif shutil.which("arecord"):
        wav = os.path.join(out_dir, f"rec_{_stamp()}.wav")
        cmd = ["arecord", "-q", "-d", str(seconds), "-f", "S16_LE", "-r", "16000", "-c", "1", wav]
        tool = "arecord"
    else:
        return None, ("[ERROR] 這台機器沒有可用的錄音工具（WSL 的 ffmpeg.exe 或 Linux 的 arecord），不能用麥克風。"
                      "下一步：請使用者提供錄好的音檔，改用 --file 音檔 辨識。")
    print(f"🎤 錄音 {seconds} 秒（{tool}）...", file=sys.stderr)
    r = run_shell(cmd, seconds + 20, merge_stderr=True)
    if r.spawn_error:
        return None, f"[ERROR] 沒辦法啟動 {tool}：{r.spawn_error}。下一步：請使用者確認錄音工具，或改用 --file 音檔。"
    if r.timed_out:
        return None, (f"[ERROR] 錄音逾時：{tool} 超過 {seconds + 20} 秒沒有結束（麥克風裝置可能沒有回應），已結束。"
                      f"下一步：請使用者確認麥克風，或改用 --file 音檔。")
    if r.rc != 0 or not os.path.exists(wav):
        tail = "\n".join((r.out + r.out_tail).strip().splitlines()[-6:])
        return None, (f"[ERROR] 錄音失敗（{tool} exit code {r.rc}）：麥克風裝置或權限有問題。下一步：請使用者確認麥克風"
                      f"（Linux 用 arecord -l 看裝置），或提供錄好的音檔改用 --file。\n{tail}")
    if tool == "ffmpeg.exe":
        dst = os.path.join(out_dir, f"rec_{_stamp()}.wav")
        shutil.copy2(wav, dst)
        wav = dst
    return wav, None


def transcribe(audio, lang, timeout):
    """在子程序裡辨識 → (段落 [(開始, 結束, 文字)], 資訊 dict, 錯誤或 None, 是否逾時)。"""
    segs, info, errs = [], {}, []

    def on_line(raw):
        parts = raw.decode("utf-8", errors="replace").split("\t")
        if parts[0] == "SEG" and len(parts) >= 4:
            segs.append((float(parts[1]), float(parts[2]), parts[3].strip()))
        elif parts[0] == "INFO" and len(parts) >= 3:
            info["lang"], info["duration"] = parts[1], float(parts[2] or 0)
        elif parts[0] == "ERR":
            errs.append("\t".join(parts[1:]))

    r = run_shell([sys.executable, os.path.abspath(__file__), "--_worker", audio, lang or ""], timeout, on_stdout_line=on_line)
    if r.spawn_error:
        return segs, info, f"沒辦法啟動辨識程序：{r.spawn_error}", False
    if r.timed_out:
        return segs, info, None, True
    if r.rc != 0 or errs:
        detail = errs[0] if errs else "\n".join(r.err.strip().splitlines()[-6:])
        return segs, info, detail or f"exit code {r.rc}", False
    return segs, info, None, False


def worker(audio, lang):
    """子程序：載入模型、逐段印出（INFO／SEG／ERR，tab 分隔），父程序逾時時至少拿得到前面的段落。"""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(MODEL_PATH, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio, beam_size=5, language=lang or None)
        print(f"INFO\t{getattr(info, 'language', '') or ''}\t{getattr(info, 'duration', 0) or 0}", flush=True)
        for s in segments:
            text = " ".join(str(s.text).split())
            print(f"SEG\t{s.start:.1f}\t{s.end:.1f}\t{text}", flush=True)
    except Exception as e:      # noqa: BLE001
        print(f"ERR\t{type(e).__name__}: {' '.join(str(e).split())[:400]}", flush=True)
        return 1
    return 0


def _explain(detail):
    low = detail.lower()
    if any(k in low for k in ("huggingface", "connection", "resolve", "offline", "max retries", "hub")):
        return f"第一次使用要下載 {MODEL_PATH} 模型，但連不上網路", "請使用者確認網路，或先把模型下載到這台機器（STT_MODEL 指到模型資料夾）"
    if any(k in low for k in ("invalid data", "could not open", "no such file", "decod", "format")):
        return "音檔無法解碼（不是音訊檔，或格式／檔案損壞）", "確認檔案是錄音檔（wav、mp3、m4a…），或請使用者重新提供"
    if "memory" in low:
        return "記憶體不足", "換小一點的模型（STT_MODEL=base）或請使用者處理"
    return "辨識失敗", "把下面的錯誤告訴使用者"


def execute(argv):
    o, err = parse_args(argv)
    if err:
        return err
    source = None
    if o["file"]:
        audio, err = pc.resolve(o["file"], "file", noun="音檔")
        if err:
            return err
        source = o["file"]
    err = dependency_error()
    if err:
        return err
    if not o["file"]:
        audio, err = record(o["record"])
        if err:
            return err
        source = f"麥克風錄音 {o['record']} 秒（{audio}）"
    segs, info, err, timed_out = transcribe(audio, o["lang"], o["timeout"])
    if err:
        what, step = _explain(err)
        return f"[ERROR] 語音辨識失敗：{what}。下一步：{step}。\n錯誤：{pc.clip(err, 400)}"
    if timed_out and not segs:
        return (f"[ERROR] 語音辨識逾時（{o['timeout']} 秒內沒有辨識出任何一段；第一次使用要下載模型會比較久）。"
                f"下一步：--timeout 加大（上限 {MAX_TIMEOUT}）再試一次，或先剪短音檔。")
    out_dir = pc.harness_logs_dir("stt")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"stt_{_stamp()}.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(f"[{a:.1f}-{b:.1f}] {t}" for a, b, t in segs) + "\n")
    dur = info.get("duration")
    meta = "，".join(x for x in (f"長度 {dur:.1f} 秒" if dur else "", f"語言 {info.get('lang')}" if info.get("lang") else "") if x)
    if not segs:
        return f"[PASS] 辨識完成，但沒有偵測到任何語音內容（{source}{'；' + meta if meta else ''}）。請確認音檔或麥克風有收到聲音。"
    chars = sum(len(t) for _, _, t in segs)
    head = (f"[PASS] 語音辨識完成：{source}" + (f"（{meta}）" if meta else "") + f"，共 {len(segs)} 段、{chars} 字；全文存在 {out_file}")
    if timed_out:
        head = (f"[PASS] 語音辨識逾時（{o['timeout']} 秒）沒有做完：只辨識到第 {segs[-1][1]:.1f} 秒，共 {len(segs)} 段，不是全部"
                f"（{source}）；要完整的結果請 --timeout 加大或剪短音檔；目前的部分存在 {out_file}")
    lines, used = [f"## 文字（{len(segs)} 段，[開始-結束] 是距離音檔開頭的秒數）"], 0
    for a, b, t in segs:
        if used > TEXT_SHOWN_CHARS:
            lines.append(f"（後面還有 {len(segs) - (len(lines) - 1)} 段沒有列出，全文在 {out_file}，用 view_file 看）")
            break
        lines.append(f"[{a:.1f}-{b:.1f}] {t}")
        used += len(t)
    return "\n".join([head] + lines)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--_worker":
        sys.exit(worker(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
    try:
        print(execute(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] stt_engine 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
