"""常數與環境變數：水位、門檻、檔名、標記。其他模組都從這裡取值，調設定只要看這一個檔案。"""
import os
import re


# 專案根目錄（prompts/、skills_system/、logs/ 所在）：agent_core/ 的上一層
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 給模型的文字都在 prompts/（可以直接改，不用改程式；讀法見 agent_core/prompt_files.py，各檔案給誰見 prompts/README.md）：
# AGENT.md（主對話的 system prompt）、Memory.md（長期記憶）、context_modes/（兩種上下文模式的規則）、harness/（主對話的 system prompt
# 與動態區裡程式組的部分、程式核對後的提醒、工具結果的包裝）、summary/（滾動摘要）、extract/（工具回傳的提煉）、orchestra/（任務引擎：
# 規劃、worker、類型）、workflow/（工作流的判斷點）、make_skill/（草擬工作流）、vision/（附圖的影像提取）
PROMPTS_DIR = os.path.join(PROJECT_ROOT, "prompts")



# =========================================================
# 🔢 Token 計量與上下文預算（全部為「真實 token」尺度）
# =========================================================
# 計量來源：
#   - AI 回覆        → Ollama 回報的 eval_count（精確）
#   - 整體上下文大小 → Ollama 回報的 prompt_eval_count（精確；快取命中時仍為完整值，已實測），
#                     兩次呼叫之間新增的訊息以校準比估算增量
#   - 使用者輸入、工具回傳 → 字元數 ÷ chars_per_token，chars_per_token 每次呼叫後用
#                     prompt_eval_count 重新校準（Ollama 沒有 tokenize API，無法精確計數）
# 下面所有門檻因此都與 num_ctx 同一尺度，可以直接比較。

# Ollama 一次請求的 context 上限。模型本身支援更長（gemma4:e4b 為 131072），這裡是為了記憶體
# 與速度自設的；主對話、壓縮摘要、工具摘要三種 session 共用同一個值。可用 AGENT_NUM_CTX 覆寫。
# 預設從 12288 提高到 32768：system prompt（AGENT.md + SKILLS.md + Memory.md + 滾動摘要）本身約
# 3000～4000 tokens，在 12288 下佔了三成，各水位之間只剩幾百 tokens 給對話，實測兩分鐘內連壓四次、
# 每次 10～15 秒，使用上明顯遲滯。記憶體較小的設備請用環境變數設回 12288 或更低。
NUM_CTX = int(os.environ.get("AGENT_NUM_CTX", "32768"))

# 🌊 雙水位線（dual watermark）比例，皆可用環境變數覆寫。
# 硬水位（TOKEN_THRESHOLD）：呼叫模型前的最後防線，超過一定同步壓縮（ensure_context_budget），
#   確保壓縮先於 Ollama 在 num_ctx 處的靜默截斷；剩下 25% 留給模型輸出與下一則訊息。
#   （更早的版本寫死 8000 且以「字元÷4」計量，換算真實 token 約 17000，早已超過 num_ctx，永遠來不及觸發。）
# 軟水位（SOFT_TOKEN_THRESHOLD）：回合結束後（最終答案已送出、模型閒著）若超過就順手壓縮，切點落在
#   任務邊界、不擋在下一次回覆前面（after_turn_compression）；/parallel_cal on 時改在背景執行緒做。
HARD_RATIO = float(os.environ.get("AGENT_HARD_RATIO", "0.75"))
SOFT_RATIO = float(os.environ.get("AGENT_SOFT_RATIO", "0.60"))
TOKEN_THRESHOLD = int(NUM_CTX * HARD_RATIO)
SOFT_TOKEN_THRESHOLD = int(NUM_CTX * SOFT_RATIO)

# low watermark：壓縮時保留最新這麼多 token 的原文（在訊息邊界切、不拆開 EXECUTE／tool result
# 這一組），其餘與上一份滾動摘要融合成新摘要。舊版固定「保留最新 2 則」，兩則可能只有 50 tokens
# 也可能 1500 tokens，銜接感不穩定。
KEEP_RATIO = 0.15
KEEP_RECENT_TOKENS = int(NUM_CTX * KEEP_RATIO)

# 軟水位的「值不值得」門檻：保留區以外可壓的舊內容少於此數時，回合結束後不壓縮——一次摘要要花
# 一次模型呼叫（10～15 秒），只為了騰出幾百 tokens 不划算；硬水位不受此限。
MIN_COMPRESS_TOKENS = max(1000, NUM_CTX // 20)

# logs/ 歸檔保留份數（summary_*.md 與同名 .json 一起計算、一起刪除）。融合摘要相鄰兩份高度重複，
# 舊檔的價值主要是被融合淘汰的歷史細節，留最近 N 份給日後的反思機制當語料即可。可用 AGENT_SUMMARY_KEEP 覆寫。
SUMMARY_ARCHIVE_KEEP = int(os.environ.get("AGENT_SUMMARY_KEEP", "30"))

# 框架自動插入、但以 user 角色送進對話的系統訊息標記（AGENT.md「Harness Messages」有對應說明）。
# 摘要模型渲染對話時用它把這些訊息標成 [harness ...] 而不是 [user]，避免把框架的規則記成使用者偏好。
SKILL_LOADED_MARKER = "[skill loaded]"  # 使用者從選單手動載入的技能規格（附在使用者訊息後面）
HARNESS_MARKERS = (
    "[tool result]", "[vision result]", SKILL_LOADED_MARKER,
)


# 融合摘要的長度目標（字，寫進摘要 prompt）與模型輸出硬上限（token，num_predict），
# 讓滾動摘要不會越滾越長；輸出被硬上限截斷時 JSON 會解析失敗、退回原文，因此上限要留得夠寬。
# 舊值 600 字（約 300 tokens，不到 num_ctx 的 1%）：使用者偏好與進度搶同一個額度，多次融合後一路走樣。
# 使用者的原話另外由程式逐字保留（USER_WORDS_MAX_CHARS），摘要只需要寫歸納後的內容。
SUMMARY_MAX_CHARS = 1500
SUMMARY_MAX_PREDICT = 2500

# 🗣️ 使用者原話：被壓縮掉的對話裡，使用者說過的話由程式逐字保留在 system prompt（不交給摘要模型改寫），
# 超過總字數時丟最舊的並註明還有幾則、原文在哪個對話片段存檔。每則最多 USER_WORD_MAX_CHARS 字。
USER_WORDS_MAX_CHARS = int(os.environ.get("AGENT_USER_WORDS_MAX_CHARS", "2000"))
USER_WORD_MAX_CHARS = 300
# 被壓縮的對話片段也存成一份工具結果存檔（同一套 #編號，可用 result_recall 取回），存檔的「腳本」欄寫這個名稱
CONVERSATION_ARCHIVE_SCRIPT = "conversation_segment"
# 對話片段在檢索清單裡跟工具回傳分開顯示（system prompt「過去的對話片段」一節），名額與保留上限也各自獨立：
# 對話片段少、價值高，不該被大量工具回傳擠出顯示視窗，也不該被工具存檔的輪替刪掉。
CONVERSATION_ARCHIVES_SHOW = int(os.environ.get("AGENT_CONVERSATION_ARCHIVES_SHOW", "10"))
CONVERSATION_SEGMENTS_KEEP = int(os.environ.get("AGENT_CONVERSATION_SEGMENTS_KEEP", "100"))
# 附圖的視覺分析結果也存成一份存檔（同一套 #編號，檢索清單標〔附圖分析〕、可以 result_recall），「腳本」欄寫這個名稱。
# 原圖不保存，這份文字是那次附圖唯一留下來的東西、沒辦法重跑拿回來，所以保留上限跟工具回傳分開算。
VISION_ARCHIVE_SCRIPT = "vision_extract"
VISION_RESULTS_KEEP = int(os.environ.get("AGENT_VISION_RESULTS_KEEP", "100"))

# 🧠 長期記憶（Memory.md）載入上限（字元）：以前只讀最後 30 行，條目變多時最舊的規則會無聲消失。
# 現在整份載入；超過上限才丟最舊的條目，並在 system prompt 與 UI 明說還有幾條沒載入。用字元數而不是 token，
# 載入結果才不會隨 chars_per_token 校準浮動（浮動會讓 system prompt 每輪不同、KV cache 失效）。
MEMORY_MAX_CHARS = int(os.environ.get("AGENT_MEMORY_MAX_CHARS", "4000"))

# 摘要模型（壓縮摘要與工具摘要兩種獨立 session 共用）。預設 None = 與主模型相同。
# 可用 AGENT_SUMMARY_MODEL 指定同家族的小模型以減少摘要耗時（例如 gemma3:1b）；但注意：
# (1) 統一記憶體的機器（Jetson／GB10）上 CPU 卸載省不到記憶體，只省算力；
# (2) 多載一個模型可能把主模型擠出 Ollama，重載主模型的代價遠高於一次摘要；
# (3) 摘要會進入之後每一輪的 system prompt，小模型的錯誤會累積。有足夠記憶體再考慮。
# (4) 反過來說，與主模型不同的摘要模型跑在另一個 runner 程序，/parallel_cal on 的背景摘要才會真的
#     與主對話同時推論——同一個多模態模型（gemma4）目前被 Ollama 強制單 slot，做不到。
SUMMARY_MODEL = os.environ.get("AGENT_SUMMARY_MODEL", "").strip() or None

# /parallel_cal 的預設值（CLI 與 Web Console 啟動時的初始狀態），可用 AGENT_PARALLEL_CAL=1 開啟。
PARALLEL_CAL_DEFAULT = os.environ.get("AGENT_PARALLEL_CAL", "").strip().lower() in ("1", "on", "true", "yes")

# 🧩 make_skill：把使用者引導 Agent「做對」的一段對話（使用者的話、AI 的判斷、工具回傳）整理成工作流的規格
# （SkillAgent.start_skill_draft 起）。不產生腳本：執行步驟只呼叫既有技能的腳本，其餘是檢查、確認、告知。
# 草擬用的模型預設同摘要模型（AGENT_SUMMARY_MODEL，再退回主模型）；這是離線、一次性的工作，要從整段對話推論流程，
# 記憶體夠的話建議用 AGENT_SKILL_MODEL 指定較大的模型（例如 gemma4:26b）。模型只填 JSON，排版由程式做。
SKILL_MODEL = os.environ.get("AGENT_SKILL_MODEL", "").strip() or None
MAKE_SKILL_MAX_PREDICT = 4000
# 交給草擬 session 的對話紀錄上限（tokens）：超過時先縮短工具回傳（保留頭尾），還不夠才從最舊的訊息開始省略
MAKE_SKILL_TRANSCRIPT_TOKENS = int(os.environ.get("AGENT_MAKE_SKILL_TRANSCRIPT_TOKENS", "16000"))
TRAJECTORY_LOG = "trajectory.jsonl"   # logs/ 下的軌跡稽核記錄（每次腳本執行一行，跨 session 追加；已 .gitignore）

# 📄 工具結果存檔：每次腳本執行的完整原始輸出都存成 logs/tool_results/<session>_<id>_<腳本>.md（key: value 檔頭 + 原文），
# 並在 index.md 記一行（編號、時間、腳本、狀態、大小、任務、摘要回答）。摘要只讀頭尾、主對話只拿重點，被省略的細節不再是黑洞：
# 模型用 result_list／result_grep／result_view 三個技能回查，不必重跑觀察型工具。技能規格文件不存（它不是執行結果）。
# 編號＝軌跡 id，啟動時從既有存檔的最大編號續編（跨 session 不重複，見 _max_archived_id），/make_skill 與稽核對得上。
# 保留最近 N 個檔且總大小不超過上限，超過刪最舊的。
TOOL_RESULTS_DIRNAME = "tool_results"
TOOL_RESULTS_INDEX = "index.md"
TOOL_RESULTS_KEEP = int(os.environ.get("AGENT_TOOL_RESULTS_KEEP", "200"))
TOOL_RESULTS_MAX_MB = float(os.environ.get("AGENT_TOOL_RESULTS_MAX_MB", "50"))

# 🔎 工具使用檢索清單（logs/tool_results/tools_use_index.md）：跟 index.md 不同檔、不同用途——index.md 是
# 「每次執行都記一筆」的稽核清單，會隨 _prune_tool_results 一起被裁；這份只有真的觸發過任務導向擷取
# （summarize_tool_result／_result_recall，見 _append_tool_use_index）才會記一筆：編號、時間、session、檔名、
# 「使用者問題 x 原始輸出」的一句話關聯敘述（index_hint；被壓縮的對話片段則是 segment_hint）。描述整句照存、不截斷：
# 截斷後的「…」會把名稱和結論切掉，模型就認不出這筆跟現在的問題有關；長度改由 prompt 要求模型自己寫精簡。編號從啟動時既有存檔的最大編號續編（跨 session 不重複），
# 所以模型只要抄編號執行 result_recall 就能取回正確那份；檔名只是給人看／除錯用。這個檔案永遠只 append，
# 不隨舊存檔被裁掉而刪除對應行；get_system_prompt 只在 system prompt 尾端顯示最近 N 筆（_tool_use_index_block），
# 是「顯示視窗」不是資料上限。
TOOL_USE_INDEX_NAME = "tools_use_index.md"
TOOL_USE_INDEX_SHOW = int(os.environ.get("AGENT_TOOL_USE_INDEX_SHOW", "30"))
TOOL_USE_INDEX_HINT_TARGET = 60   # prompt 要求的描述長度（中文字數，一段英數路徑算 1 字）；只是給模型的目標，程式不截斷
# 看舊存檔的衍生輸出：不記進檢索清單（會跟原本那筆重複佔位，recall 到它只拿得到部分內容）
DERIVED_RESULT_SCRIPTS = {"result_grep_cmd.py", "result_view_cmd.py", "result_list_cmd.py", "result_recall_cmd.py"}
TASK_HISTORY_KEEP = 3   # 任務線：摘要錨點帶最近幾則使用者訊息（使用者回答追問時，最新一句往往只是關鍵字，原本要做什麼在前一句）
TRAJECTORY_OUTPUT_HEAD = 300          # 每筆軌跡保留的輸出開頭字元數（讓草擬模型知道結果長什麼樣）
DEFAULT_SKILL_CATEGORY = "自建技能"   # 模型選的分類不在 SKILLS.md 裡時的落點（沒有這個段落會自動建立）
SKILL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")
# 會改變狀態（建容器、送工單、寫記憶、切換目錄／容器）的技能：工作流草稿的步驟用到它們時，預覽會提醒（執行時照常確認）
NON_READONLY_SKILLS = {"docker_est", "workpackage_send", "workpackage_cancel", "overpending_cancel", "modify_memory", "change_dir", "docker_open",
                       "docker_ctl", "file_ops", "ROS2_param", "ROS2_topic_pub", "rmf_handshake", "host_runcmd", "task_run",
                       "mcap_recorder", "mcap_slicer", "ROS2_domain_id", "ROS2_workspace_env", "workflow_run"}

# 使用者角色但實為工具回傳的訊息前綴（見 _split_for_compression 的配對規則）
TOOL_RESULT_PREFIXES = ("[tool result]",)

# 工具結果訊息第二行的框架句開頭（tool_result_message）。壓縮摘要渲染時以它辨認並去掉框架句。
TOOL_RESULT_FRAME = "【系統回傳】"

# 字元→token 校準比的預設值與合理範圍。中文為主的內容實測約 1.8～1.9 字元/token。
DEFAULT_CHARS_PER_TOKEN = 1.9
MIN_CHARS_PER_TOKEN, MAX_CHARS_PER_TOKEN = 1.0, 6.0

# 單一工具回傳內容的 token 門檻：超過此值時，不把完整原始內容塞進主對話（避免一次搜尋／列目錄／
# topic 擷取的大量輸出把 context 灌爆、干擾推理），而是交給獨立的摘要 session（summarize_tool_result）
# 拿「完整原始輸出 + 使用者目標 + 這一步的目的」做任務導向擷取，主對話只收到重點；完整內容仍會顯示給
# 使用者（CLI 印出、或 Web Console 的系統/工具回傳面板）。約 1000 字元。
# （舊值 250 是「字元÷4」尺度，換成真實尺度即為 500。）
TOOL_RESULT_TOKEN_THRESHOLD = 500

# 🧠 任務導向摘要（Task-Oriented Summarization）：超過門檻的工具回傳一律走這條路，沒有腳本自帶的豁免
# （舊版 [PASS][digest] 讓分析型輸出放寬到 1500 tokens 直接進主對話，等於由腳本決定什麼重要——已移除，
# 腳本改回傳完整資訊，重要與否交給知道任務的獨立 session 判斷）。唯一例外是技能規格文件（SKILL_DOC_PREFIX）。
# 預設開啟；/summarize off 或 AGENT_TOOL_SUMMARY=0 改回只給成功／失敗判定（不多花一次模型呼叫）。
TOOL_SUMMARY_DEFAULT = os.environ.get("AGENT_TOOL_SUMMARY", "1").strip().lower() not in ("0", "off", "false", "no")
# summarize_tool_result() 產生的內容固定以這個標籤開頭：CLI 據此印出、Web 據此推 🧠 卡片，讓使用者看到主對話實際收到的內容。
TOOL_SUMMARY_TAG = "[tool result - 任務導向摘要]"
# analysis_run 的回傳（程式整理好的事實報告）固定以這個開頭：它本身就是整理好、有編號的事實，跟 result_recall
# 一樣不再交給摘要 session（is_exempt_result），主對話直接收到完整的報告。
ANALYSIS_REPORT_HEAD = "[PASS] 📊 數據事實報告"
# 報告最後一行（給主對話的回答說明）的開頭：turn_guard 核對回答時，這一行的字（「不要寫成誰導致…」）不算報告裡本來就有的字
ANALYSIS_ANSWER_NOTE = "（依這份報告回答使用者"
# _content_for_context 退回「只給成功／失敗判定」時的固定開頭（/summarize off 或摘要 session 失敗）；UI 據此標示 AI 實際收到的是哪一種。
TOOL_REDUCED_TAG = "[tool result - 已精簡]"
# 🧩 工具回傳的提煉（agent_core/extract.py；summarize_tool_result 與 result_recall 共用）：程式依原文的結構切段 → 每段一個 worker
# 摘出跟問題有關的事實（附原文的行號，程式核對名稱與數值）→ 整合成交給主對話的重點。只有一段時一次呼叫直接寫結果。
# 全文都會讀（以前超過 16000 字只讀頭尾，中間的內容主對話永遠看不到）；每一次的切段、各段的結果、核對、整合都存在 logs/extract_jobs/<編號>/。
EXTRACT_CHUNK_CHARS = int(os.environ.get("AGENT_EXTRACT_CHUNK_CHARS", "8000"))   # 每段最多幾個字（≈4200 tokens；worker 的輸入）
# 一次提煉最多讀幾段（≈ 8 × 8000 字）：更長的依跟問題的關係（問題裡的名稱、數字出現在哪幾段）挑，沒讀的行號範圍由程式寫進「未涵蓋」，
# 主對話可以用更具體的問題 result_recall（再挑一次）或 result_view 看那一段。模型呼叫是一個一個排隊的（Ollama 同一個模型一個 slot），段數就是等待時間。
EXTRACT_MAX_CHUNKS = int(os.environ.get("AGENT_EXTRACT_MAX_CHUNKS", "8"))
EXTRACT_PARALLEL = int(os.environ.get("AGENT_EXTRACT_PARALLEL", "2"))   # 同時送出幾個 worker（同一個模型時只是重疊網路與排隊）
EXTRACT_WORKER_FACTS = 12           # 每個 worker 最多摘幾條事實（寫進 prompt）
EXTRACT_EVIDENCE_CHARS = 12000      # 交給整合的「事實引用的原文」最多幾個字（超過的事實只給行號、不附原文）
# 交給主對話的重點的長度目標（字，寫進 prompt）：原文的四分之一，介於 400～1500 字。以前固定 400 字，長的輸出（12 台車、幾十個錯誤）主對話
# 只拿得到幾條，使用者一問細節就要回存檔；工具回傳門檻 500 tokens ≈ 950 字，摘要不比原文短時主對話直接收到原文（turn._content_for_context）。
EXTRACT_SUMMARY_MIN_CHARS, EXTRACT_SUMMARY_MAX_CHARS = 400, 1500
EXTRACT_WORKER_PREDICT = 1500       # worker 輸出的 num_predict 上限（被截斷時 JSON 解析失敗，那一段記成提煉失敗、寫進未涵蓋）
EXTRACT_SYNTH_PREDICT = 2500        # 整合（與一次寫完）的 num_predict 上限
EXTRACT_JOBS_DIRNAME = "extract_jobs"
EXTRACT_JOBS_KEEP = int(os.environ.get("AGENT_EXTRACT_JOBS_KEEP", "500"))   # 提煉的存檔只留最近幾次（每次幾十 KB：prompt 含那一段的原文）
RECALL_MAX_RECORDS = 3   # result_recall 一次最多讀幾份存檔（幾份的段落交給 worker，同一個整合看全部）

# run_tool 載入技能規格文件時回傳字串的固定開頭。規格文件是「按需載入」機制的核心，
# 內容（尤其是實際腳本路徑與參數格式）必須完整進入上下文，因此 _content_for_context
# 對這類結果一律放行、不套用 TOOL_RESULT_TOKEN_THRESHOLD，Web Console 也不標記 ⚠️。
# 規格書本身仍應維持精簡（以 400 tokens／約 800 字元以內為原則），節省每次載入的上下文成本。
SKILL_DOC_PREFIX = "📘 已載入技能"
# 舊的流程技能（第 3 階段以前 /make_skill 產生的；現在產生工作流，讀取的程式第 6 階段清掉）：規格 frontmatter 的 type。沒有自己的腳本，步驟是「執行既有技能／向使用者確認／檢查回傳／告知」，
# 載入時告訴模型照步驟一步一步做（dispatch），也不拿它來對照「腳本屬於哪個技能」（trajectory._script_skill_map）。
PROCEDURE_DOC_TYPE = "Procedure"

# =========================================================
# 🔀 上下文管理模式（/context_mode harness|claude_code；AGENT_CONTEXT_MODE 設預設值）
# harness：harness 替模型做決定——大量回傳交給獨立 session 依問題擷取、附下一步建議（原本的設計）。
# claude_code：相信模型——回傳原文直接進上下文（太大保留頭尾＋存檔編號），要查細節、要不要委派獨立 session
#   （result_recall）由模型自己決定；harness 只提供截斷、清除舊回傳、滾動摘要這些安全網。
# 兩種模式共用：原文存檔、檢索清單、執行前關卡、記憶、滾動摘要。規則文字在 prompts/context_modes/<模式>.md。
# =========================================================
CONTEXT_MODES = ("harness", "claude_code")
CONTEXT_MODE_DEFAULT = os.environ.get("AGENT_CONTEXT_MODE", "harness").strip().lower()
if CONTEXT_MODE_DEFAULT not in CONTEXT_MODES:
    CONTEXT_MODE_DEFAULT = "harness"
CONTEXT_MODES_DIRNAME = "context_modes"
# claude_code 模式：單一工具回傳進主對話的上限（token）。超過時保留頭尾（6:4），中間換成一行「省略多少、存檔編號、怎麼查」。
# 預設 3000 ≈ num_ctx 32768 的 9%（Claude Code 的 Bash 輸出上限約 30000 字元，對 200K context 約 4%；小 context 給寬一點）。
RAW_RESULT_MAX_TOKENS = int(os.environ.get("AGENT_RAW_RESULT_MAX_TOKENS", "3000"))
# claude_code 模式：上下文超過水位時，先把舊的工具回傳清成「#編號」佔位（原文在存檔，可還原），不夠才做滾動摘要。
# 最新 CLEAR_KEEP_RECENT_RESULTS 則不清；小於 CLEAR_MIN_TOKENS 的不清（省不了多少，還會讓 KV cache 從那裡開始失效）。
CLEAR_KEEP_RECENT_RESULTS = int(os.environ.get("AGENT_CLEAR_KEEP_RESULTS", "3"))
CLEAR_MIN_TOKENS = 300
TOOL_TRUNCATED_TAG = "[tool result - 原文頭尾]"   # claude_code 模式超過上限、中間被截掉的回傳（UI 依此標示）
TOOL_CLEARED_TAG = "[tool result - 已清除]"       # 被清成佔位的舊回傳

# =========================================================
# 🛡️ 執行前關卡：會改變實體／外部狀態的技能，執行前一律由程式要求使用者確認（不靠模型記得要問）。
# 跟 Plan 模式同一個原則：關卡由程式路徑保證——run_tool 沒拿到 approved=True 就不執行這些技能。
# docker_runcmd 的指令若被判定為唯讀（ls、cat、ros2 topic echo…，見 guard.is_readonly_shell）則放行；
# workpackage_send 加 --dry-run 只顯示不送，也放行。change_dir／docker_open 只改 harness 自己的狀態，不擋。
# AGENT_GUARDED_SKILLS 可覆寫清單（逗號分隔，none＝全部不擋）；/guard off 只對目前 session 關閉。
# =========================================================
_GUARDED_DEFAULT = ("workpackage_send,workpackage_cancel,overpending_cancel,docker_est,docker_runcmd,"
                    "host_runcmd,docker_ctl,file_ops,ROS2_param,ROS2_topic_pub,ROS2_domain_id,ROS2_workspace_env,rmf_handshake,task_run,"
                    "workflow_run")
_guarded_env = os.environ.get("AGENT_GUARDED_SKILLS", _GUARDED_DEFAULT).strip()
GUARDED_SKILLS = set() if _guarded_env.lower() in ("", "none", "off") else {s.strip() for s in _guarded_env.split(",") if s.strip()}
GUARD_DEFAULT = os.environ.get("AGENT_GUARD", "1").strip().lower() not in ("0", "off", "false", "no")
GUARD_DENIED_TAG = "[DENIED]"

# =========================================================
# ⏱️ 每次模型呼叫的耗時記錄（logs/perf.jsonl）：Ollama 回報的 prompt_eval_count 在 KV cache 命中時仍是完整值，
# 看不出 cache 有沒有命中；prompt_eval_duration 才看得出來（命中時只算新的部分）。每筆記呼叫種類、token、毫秒、
# 以及主對話呼叫前「system prompt 有沒有變」「中間跑了幾次獨立 session」，evals/chat/perf_report.py 依此分組比較。
# =========================================================
PERF_LOG = "perf.jsonl"
PERF_LOG_ENABLED = os.environ.get("AGENT_PERF_LOG", "1").strip().lower() not in ("0", "off", "false", "no")


# 單一工具腳本的總逾時（秒）：harness 的最後防線。各腳本自身應設定更短的逾時
# （容器類腳本可調的上限 570 秒就是為了低於這個值），這裡只處理腳本本身卡死
# （例如程序內無法中斷的重運算、讀取無回應的裝置）的情況，避免整個 Agent
# （CLI 與 Web Console 都在同一條執行緒上等待工具）被無限期卡住。
TOOL_EXEC_TIMEOUT = 600

# =========================================================
# 🧠 模型的 thinking 與設定檔
# 主對話的開關；模型不支援 thinking 時一律不送（Ollama 會回 400）。預設關：主對話要的是照格式的 JSON 決定，思考會多花時間。
# Web Console 的「🧠 模型」可以切換（存檔：logs/model_settings.json）。注意：有些模型關掉也還是會思考（deepseek-r1）。
# =========================================================
MAIN_THINK_DEFAULT = os.environ.get("AGENT_MAIN_THINK", "").strip().lower() in ("1", "on", "true", "yes")
MODEL_SETTINGS_NAME = "model_settings.json"   # logs/ 下：Web Console 設定的主對話模型與 thinking 開關，重開也記得

# 🧩 工作流（agent_core/workflow.py、workflow_spec.py；workflow_run 偽技能）：skills_system/workflows/<名稱>.md 的步驟由程式推進，
# 模型只在判斷點（填這一步的值、選分支）出手；每一次的步驟、判斷點的模型呼叫存在 logs/workflow_jobs/<編號>/
WORKFLOW_JOBS_DIRNAME = "workflow_jobs"
WORKFLOW_JOBS_KEEP = int(os.environ.get("AGENT_WORKFLOW_JOBS_KEEP", "300"))
WORKFLOW_CONTEXT_CHARS = int(os.environ.get("AGENT_WORKFLOW_CONTEXT_CHARS", "3000"))   # 判斷點看前面每一步的輸出最多幾字（完整的在存檔）
WORKFLOWS_ENABLED = os.environ.get("AGENT_WORKFLOWS", "1").strip() != "0"   # 0：不列工作流、不接受 workflow_run（評測「沒有工作流」的對照）
# workflow_run 的報告固定以這幾個開頭（agent_core/workflow.py 的報告、列表、取消都用它們）：跟 analysis_run 的事實報告一樣是程式整理好的，
# 不再交給提煉 session（is_exempt_result），主對話直接收到完整的報告（2026-10-23 實測：一份 1000 字的報告被提煉了一次，多一次模型呼叫）
WORKFLOW_REPORT_HEADS = ("[PASS] 工作流 ", "[PASS] ⏸️ 工作流 ", "[ERROR] 工作流 ")

# 🧭 任務引擎（agent_core/task_engine.py，task_run 偽技能；Plan 模式也用它）：規劃 → 程式檢查 → 先查 → 依事實重排 → 確認 → 每一步一個
# worker（或一個工作流）→ 程式檢查 → 程式寫報告。類型（profile）在 prompts/orchestra/profiles/；每一次的計畫、每一步、每一次模型呼叫存在
# logs/task_jobs/<編號>/
TASK_MAX_ITEMS = 6                       # 計畫最多幾步（小模型規劃太多步時後面的步驟品質差，也難確認）
TASK_WORKER_MAX_STEPS = 10               # 每一步的 worker 最多幾輪（每輪一個動作）
TASK_MAX_REPLANS = 2                     # 一個任務最多重排幾次（先查完一次、某一步失敗一次）
TASK_JOBS_DIRNAME = "task_jobs"
TASK_JOBS_KEEP = int(os.environ.get("AGENT_TASK_JOBS_KEEP", "300"))
# task_run 的報告固定以這幾個開頭：程式整理好的（每一步的結果、核對過的事實），不再交給提煉（is_exempt_result）
TASK_REPORT_HEADS = ("[PASS] 任務", "[PASS] ⏸️ 任務", "[ERROR] 任務")

# =========================================================
# 📊 數據分析（agent_core/analysis_job.py，analysis_run 技能）：只要有 .mcap 就能用的事實報告——量到什麼、什麼時候、Log 說了什麼，
# 不做因果推論（原因要對照源碼另外分析；第九輪的源碼脈絡與因果推論留在 doc/archive/root_cause_reference/）。2026-10-23 起全部由程式做：
# rosout_parser 把 Log 去重成唯一訊號；mcap_analyzer --facts 量全部的 Topic、全部的 Key，整理成有編號的事實（T#＝Topic、E#＝事件、
# L#＝Log）、時間線與重要的時間點，重點照規則寫，不呼叫模型。模型在主對話依報告回答（回答寫的變化與值由程式核對，agent_core/claims.py）。
# 每次的產物在 logs/analysis_jobs/<編號>/。
# =========================================================
ANALYSIS_JOBS_DIRNAME = "analysis_jobs"
ANALYSIS_JOBS_KEEP = int(os.environ.get("AGENT_ANALYSIS_JOBS_KEEP", "300"))   # 只留最近幾次（每次幾百 KB：事實、報告、索引）
ANALYSIS_SETTINGS_NAME = "analysis_settings.json"   # logs/ 下：數據根目錄、預設容器（Web 的 📊 分析面板 ⚙️ 設定）
# 數據根目錄（容器內或主機路徑都可以，主機路徑會依 bind mount 換成容器路徑）：mcap_recorder 錄到這裡、實驗名稱與 latest 相對於它；
# 沒設定時工具在容器的 /workspace 底下找 experiment_logs
ANALYSIS_DATA_ROOT = os.environ.get("AGENT_ANALYSIS_DATA_ROOT", "").strip()
# 一次分析最長幾秒（以整秒算）：量整段數據，事實才不會漏掉一段。更長的數據先用 mcap_slicer 切成這個長度以內的片段再分析
ANALYSIS_MAX_SECONDS = int(os.environ.get("AGENT_ANALYSIS_MAX_SECONDS", "180"))
# 事實的對照（程式）：Topic 的變化與 Log 前後這麼多秒內就列在一起（只寫時間差，不代表誰造成誰）；不同 Topic 這麼多秒內一起變化＝「同時」
ANALYSIS_ALIGN_SEC = 1.0
ANALYSIS_SAME_TIME_SEC = 0.1
