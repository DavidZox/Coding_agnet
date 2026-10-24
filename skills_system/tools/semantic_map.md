---
type: Tool
title: 語義地圖與目前佈局
description: 站點（名稱、節點 id、語意名稱）、說明、路段，對應目前機器人與 work package 在哪；也可只列站點或機器人。
version: 1.2.1
dependencies: ["fih_rmf_system web_console (port 8020)"]
---

# 用途
web_console `GET /api/topology`（拓譜圖＋semantics.yaml）加一幀快照，永遠是 web_console 目前載入的場域。發送前確認站點、使用者問「某站是什麼／誰在那裡」時用。有些地圖的站沒有名稱（例如 fih_humanoid_amrScene_v2）：這種站寫成 `id 5`，送工作包寫 id（5）或語意名稱。

# 語法
`EXECUTE: scripts/semantic_map_cmd.py [關鍵字或站點] [--stations] [--robots] [--url 位址]`
* 不帶參數：`## 站點`（每站一行：名稱｜id｜語意名稱）、`## 目前有機器人或工作包的站`、`## 機器人`。
* 帶關鍵字、站點名稱或 id：每站一筆 `--- #n`（說明、目前狀況、連接路段），最多 12 站、12 路段，其餘寫「另有 N 個」。含空白請用引號。
* `--stations`：只列站點；`--robots`：機器人（名冊＋目前狀態）。`--url`：預設環境變數 `RMF_WEB_CONSOLE_URL` 或 http://localhost:8020。

# 範例
`EXECUTE: scripts/semantic_map_cmd.py`　`EXECUTE: scripts/semantic_map_cmd.py 包裝區`　`EXECUTE: scripts/semantic_map_cmd.py p5`　`EXECUTE: scripts/semantic_map_cmd.py --robots`

# 回傳
`[PASS] 語義地圖：N 站（有名稱 a、只有 id b；有語意名稱 c）、M 路段…` + 各節；快照讀不到時第一行註明，仍回地圖。

# 異常
* 找不到關鍵字（`[ERROR]`，附相近的）：換關鍵字，或 `--stations` 看全部。
* 拓譜圖沒有站點、沒有任何機器人：請使用者確認 web_console 載入的場域。
* 連不上 web_console：回報使用者；版本沒有 /api/topology（404）時 `--stations` 會改用 /api/stations。
