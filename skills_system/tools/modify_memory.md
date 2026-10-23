---
type: Tool
title: 寫入經驗記憶
description: 寫入長期記憶（Memory.md，每輪常駐 system prompt）；一條最多 300 字。
version: 3.1.0
dependencies: []
---

# 用途
把使用者明確要求記住的經驗寫入長期記憶 `Memory.md`，之後每一輪的 system prompt 都會帶著它：適合通用原則、選技能的規則（例如「list_dir 不能看容器內」）、某個技能的用法或前置條件、溝通風格、專案經驗。不要寫某個時間點的狀態（「系統整體健康」這類），它會過期。

# 語法
`EXECUTE: scripts/modify_memory_cmd.py "問題種類 | 問題描述 | 解決方法或結論"`
* 只有記憶內容、沒有任何選項；整條用引號包住（內容裡有 `--filter` 這種字也沒關係）。
* 一條最多 300 字（記憶總共只載入 4000 字，太長會把舊的擠掉）；細節寫成檔案，記憶只寫結論與檔案路徑。

# 範例
`EXECUTE: scripts/modify_memory_cmd.py "偏好問題 | 使用者偏好繁體中文 | 後續回答優先使用繁體中文"`
`EXECUTE: scripts/modify_memory_cmd.py "技能用法 | 數某類檔案 | list_dir 用 --filter 計數，子目錄用 find_file"`

# 回傳
`[PASS] 成功寫入長期記憶（…；N 字，目前共 M 條）` + `Memory: [時間] 內容`；相同內容已存在時 `[PASS]` 提示未重複寫入。

# 異常
* `[ERROR] 記憶內容不可為空`：給內容。`[ERROR] 超過上限 300 字`：精簡成一句再寫。
* `[ERROR] modify_memory 沒有任何選項`：整個參數是 `--xxx` 時出現；只給內容，內容含 `--` 開頭的字就整條加引號。
* `[ERROR] 記憶寫入失敗`：告訴使用者。禁止寫入敏感資訊、過長 log、未確認的推測。
