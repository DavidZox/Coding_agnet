---
type: Tool
title: 語音轉文字
description: 把音檔（--file）轉成文字；使用者要用說的時候也可以用麥克風錄音後辨識（faster-whisper）。
version: 2.0.0
dependencies: ["faster_whisper", "arecord 或 ffmpeg.exe（只有麥克風模式要）"]
---

# 用途
* `--file 音檔`：辨識已經存在的錄音（wav、mp3、m4a、flac、ogg…），不需要有人在旁邊，AI 可以自己用。
* 不給 --file：麥克風錄音後辨識，只在使用者說要用講的時候用（要有人對著麥克風說話；WSL 用 Windows 的 ffmpeg.exe、Linux 用 arecord）。
辨識結果全文寫在 harness 的 logs/stt/（路徑在輸出裡），不寫進工作目錄。

# 語法
`EXECUTE: scripts/stt_engine_cmd.py [--file 音檔] [--lang 語言] [--record 秒數] [--timeout 秒數]`
* `--lang`：zh、en…（預設自動偵測）。`--record`：錄音秒數，預設 10、上限 60。
* `--timeout`：辨識的上限，預設 300 秒、上限 570（第一次使用要下載模型會比較久）；逾時保留已經辨識出的段落。

# 範例
`EXECUTE: scripts/stt_engine_cmd.py --file recordings/meeting.m4a --lang zh`　`EXECUTE: scripts/stt_engine_cmd.py --record 15`

# 回傳
`[PASS] 語音辨識完成：<來源>（長度 N 秒，語言 zh），共 K 段、M 字；全文存在 <路徑>`，接 `## 文字（K 段…）`，每行 `[開始-結束] 文字`
（秒數從音檔開頭算）。沒有聲音：`[PASS] 辨識完成，但沒有偵測到任何語音內容`。逾時但有部分：`[PASS] … 逾時沒有做完…不是全部`。

# 異常
* `[ERROR] 缺少 Python 套件 faster-whisper`：照訊息把安裝指令告訴使用者，不要自己安裝。
* `[ERROR] 找不到音檔`：照相近的路徑修正。`音檔無法解碼`：確認是錄音檔。`連不上網路`（下載模型）：告訴使用者。
* `[ERROR] 沒有可用的錄音工具`、`錄音失敗`、`錄音逾時`、`無法建立錄音暫存目錄`、`沒辦法啟動`：麥克風問題，請使用者處理或提供錄好的音檔（--file）。
* `[ERROR] 語音辨識逾時`：--timeout 加大或剪短音檔。`不認識的參數`、`--record／--timeout 要是…秒數`、`後面需要值`：照語法改。
