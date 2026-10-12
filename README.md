# Coding_agent_harness

以本地 Ollama 模型（預設 `gemma4:e4b`）為核心的 **coding agent**，從 [AI_agent_harness](../AI_agent_harness) 延伸而來：原本的技能系統（索引＋按需載入的規格＋既有腳本）、上下文管理、執行前關卡、記憶、Plan 模式、CLI 與 Web Console 全部保留（機器人維運的技能也還在），再加上一個 **coding orchestrator**——像 Claude Code 一樣做長時間、跨檔案的程式開發（**Python、C、C++**）：先探索專案、列出計畫，你核准後派 **coding worker** 一項一項修改，每一項由程式驗證（語法、跨檔 import、C／C++ 編譯、**真的 pytest／GoogleTest**），可以暫停、停止、隨時還原全部變更。決策模型只用本地模型。長任務的能力用公開的 [DevBench](evals/devbench/README.md)（照規格從零寫出整個專案）量過。

## Coding orchestrator（這個專案新增的部分）

```
你 ──任務──▶ 主對話的 AI（code_job_send）／🧑‍💻 Code 按鈕／/code 指令
                  │
                  ▼
coding orchestrator（背景服務，狀態都在 logs/coding_jobs/<編號>/）
  ① 探索：repo_map 腳本算好專案地圖（檔案、類別／函式與行號、測試指令）——不用模型自己摸索
  ② 規劃：規劃 session 先挑要讀的檔案，再拆成 work items（每一項：要改的檔案、要做的事、驗證指令）
     harness 檢查並修正計畫：路徑寫錯自動對到真的檔案、goal 提到的類別／函式在哪個檔案由 AST 索引補上
  ③ ⏸ 你在 Coding 面板核准（可以逐項編輯、調順序、用說的改）——核准前不會改任何檔案
  ④ 每一項派一個 coding worker：乾淨的 session＋自己的工具迴圈（看檔、搜尋、code_refs → 修改 → 跑測試）
     worker 回報完成 → 程式驗證：語法、未定義名稱、跨檔 import（C／C++ 用 gcc／g++ 編譯）、對照規格的函式簽名、
                       這一項的測試（pytest；C／C++ 建置後跑 GoogleTest）
     沒過 → 錯誤交還 worker 修（最多 3 次）→ 換新的 worker 帶著失敗原因重試 → 仍失敗就停下來問你
  ⑤ 整體驗證（通常是全部測試）→ 沒過派一個修正 worker
  ⑥ 報告（Coding 面板、report.md，也存成主對話的 #編號，之後可以直接問「剛剛改了什麼」）
```

![Coding orchestrator 的流程](doc/images/Coding_orchestrator的流程.png)

**兩個關鍵的設計（都是實測小模型之後決定的，細節見〈[設計筆記 2.12](doc/設計筆記與已知限制.md)〉）**：

- **worker 的「決定」走 JSON、「程式碼」走純文字**：每一步 worker 用 `{thought, reply, action}` 決定要做什麼（跟主對話同一個協議，只看 action）；要改檔時 harness 另開一個乾淨的 session，請模型用一般文字輸出整份檔案或 SEARCH/REPLACE 區塊。實測 e4b 把程式碼塞進 JSON 字串時反斜線少跳脫一層（3/3 寫錯），放在 ``` 區塊裡 3/3 正確；接在 JSON 對話後面要內容時，它會一直回 JSON，所以內容通道是獨立的 session。
- **能由程式做的就不交給模型**：專案地圖、名稱定義在哪、測試通過幾個、SEARCH 對不對得上（逐字→忽略行尾空白→忽略縮排，自動剝掉抄進來的行號）、「其餘不變」這種偷懶的省略、改壞語法、跨檔 import 對不上，全部由腳本判斷；改檔前一律備份。

### 怎麼用（Web Console）

```bash
~/aiagent_venv_env/.venv/bin/python web_console.py    # http://127.0.0.1:8765
```

1. **設定工作區**：右欄切到「🧑‍💻 Coding」→ ⚙️ 設定，填專案根目錄（或輸入 `/code_ws /path/to/project`）。沒設定時用主對話的工作目錄（標題列的 cwd）。
2. **送出任務**（三種方式擇一）：按輸入框旁的 **🧑‍💻 Code**（變藍色＝Code 模式，之後送出的任務都交給 orchestrator）；或輸入 `/code <任務>`；或直接跟 AI 說（它會用 `code_job_send` 交出去）。任務寫清楚要做什麼、使用範例、要不要測試。
3. **核准計畫**：左欄會出現「📋 計畫列好了」；右欄 Coding 面板逐項列出要改的檔案與驗證指令。可以 ✏️ 直接改每一項、↑↓ 調順序、🗑️ 刪除、＋ 新增，或在文字框用說的改，最後按「✅ 核准並開始」。
4. **看進度**：每一項的卡片會展開顯示 worker 每一步的想法（💭）、動作（▶）、工具結果（✅／❌，可展開細節）、驗證結果；標題列與分頁標籤顯示進度。某一項試了兩次都沒通過時會停下來問你：🔁 重試（可以補充說明給 worker）、⏭ 跳過、⏹ 停止。
5. **看結果**：「變更的檔案」點一下看彩色 diff；「📄 報告」開完整報告；不滿意按「↩ 還原全部變更」。

| coding 指令 | 作用 |
|---|---|
| `/code <任務>` | 交給 coding orchestrator（探索→計畫→你核准→worker 修改並驗證） |
| `/code`、`/code jobs` | 看目前的 job／列出最近的 job |
| `/code approve`、`/code pause`、`/code resume`、`/code cancel` | 核准計畫、暫停、繼續（程式重新啟動而中斷的 job 也是用它接著做）、停止（目前這一步做完才停） |
| `/code retry\|skip\|stop [N] [補充]` | 某一項失敗、在等你決定時 |
| `/code revert N` | 把 job #N 改過的檔案全部還原 |
| `/code_ws <路徑>`、`/code_model planner\|worker\|all <模型>` | 工作區、規劃與 worker 的模型（例如 `/code_model planner gemma4:26b`） |
| `/model [模型]`、`/think main\|planner\|worker on\|off` | 查看三個角色的模型／換主對話（非 coding）的模型；各角色的 thinking 開關（同標題列的 🧠） |
| `/code_python <路徑>\|-` | 跑 Python 測試用的直譯器（`-`＝自動：工作區的 `.venv`／`venv` → harness 的 Python） |
| `/code_mode on\|off`、`/code_autoapprove on\|off` | Code 模式（同 🧑‍💻 按鈕）、計畫自動核准（無人看管時用） |

CLI（`python3 Agent_Runner.py`）有同樣的 `/code` 指令：會在終端機跟著顯示進度，計畫要你輸入 y 核准（或直接打修改意見），某一項失敗時問 r／s／x。

| coding 設定（環境變數） | 預設 | 說明 |
|---|---|---|
| `AGENT_CODING_PLANNER_MODEL`／`AGENT_CODING_WORKER_MODEL` | 同主模型 | 規劃與 worker 的模型（Web 也可以在 ⚙️ 設定、🧠 或 `/code_model` 切換） |
| `AGENT_CODING_THINK`／`AGENT_CODING_WORKER_THINK` | 關 | 規劃／worker 的 thinking 模式（Web：⚙️ 設定或 🧠；模型支援 thinking 才會送） |
| `AGENT_CODING_ON_FAIL` | `ask` | 某一項試完仍失敗：`ask` 停下來問／`skip` 跳過／`stop` 停止 |
| `AGENT_CODING_AUTO_APPROVE` | 關 | 計畫列好自動核准 |
| `AGENT_CODING_WORKER_STEPS` | 18 | 一個 worker 最多幾個動作 |
| `AGENT_CODING_WHOLE_FILE_LINES` | 250 | 改既有檔案時請模型輸出整份的上限（更長的用 SEARCH/REPLACE） |
| `CODE_ALLOW_INSTALL` | 關 | 放行 worker 的 pip／npm 安裝指令 |
| `CODE_PYTHON` | 自動 | 跑 Python 測試與程式的直譯器（Web：⚙️「測試用的 Python」） |
| `CODE_CPP_PREFIX` | `~/.local` | C／C++ 函式庫（gtest 等）的安裝位置，冒號分隔；加進 `CPATH`、`LIBRARY_PATH`、`CMAKE_PREFIX_PATH` |

**安全**：核准前不會改檔案；worker 只能寫工作區內的檔案（不能動 `.git/`）；指令有安全檢查（擋 sudo、rm／mv、chmod、網路、安裝套件、會改版本紀錄的 git、`sed -i`、寫到工作區外的轉向——刪檔要用 `code_write --delete`，才有備份）；每個檔案第一次被改之前都備份到 `logs/coding_jobs/<編號>/backup/`。這是啟發式的擋法（例如 `python3 -c` 裡的程式碼不會被逐行檢查），所以工作區請設在專案目錄、重要的專案請用 git。主對話本身不能改檔（`code_edit`／`code_write`／`code_run` 只給 worker 用），停止 job（`code_job_cancel`）要經過執行前確認。

### 新增的技能

| 技能 | 用途 |
|---|---|
| `repo_map` | 專案地圖：目錄樹＋每個程式檔的類別與函式（行號範圍；Python 用 AST、C／C++ 用掃描器）＋測試指令、建置系統（CMake／Makefile）與 git 狀態 |
| `code_view` | 帶行號讀檔：整份、某一段，或 `--symbol` 只看某個函式／類別（`Inventory.remove`、`Circle::area`） |
| `code_search` | 整個專案的程式碼搜尋（略過 venv、build、.git），附行號與前後文 |
| `code_refs` | 某個名稱在哪裡定義、宣告（C／C++ 標頭）、被誰匯入與使用；改名或改參數前列出要一起改的地方 |
| `code_check` | 靜態檢查：Python 的語法、未定義名稱、專案內 import；C／C++ 用 gcc／g++ 編譯一次；`--spec` 對照規格文件裡的函式簽名 |
| `code_test` | 跑測試：Python 用 pytest、C／C++ 建置後跑 GoogleTest（CMake＋ctest、`make test`，或直接用 g++ 編譯）；通過／失敗數由腳本算好，失敗附期望值與實際值、編譯失敗附「檔案:行號」 |
| `code_diff` | 看某個 coding job 或 git 工作區改了什麼 |
| `code_job_send`／`code_job_status`／`code_job_cancel` | 主對話把修改程式的任務交給 orchestrator／查進度／停止 |
| `code_edit`／`code_write`／`code_run` | worker 專用：修改既有檔案／建立或刪除檔案／在工作區執行指令 |

原本的 `code_ast_reader`（單一 Python 檔的結構）保留，worker 也可以用。

### Python、C、C++ 與測試

同一個 orchestrator 改 Python、C、C++，測試**一律用真的 pytest 與 GoogleTest**（原本沒有 pytest 時用的內建 runner 已移除——要驗證就要用跟你平常一樣的工具）：

- **Python**：`code_test` 用專案的 Python 跑 pytest——工作區有 `.venv`／`venv` 就用它（專案的相依套件在那裡），或在 ⚙️ 設定「測試用的 Python」指定；都沒有就用 harness 的 `~/aiagent_venv_env/.venv`（已裝 pytest）。那個 Python 沒有 pytest 時會回報安裝方式，不會假裝跑過。
- **C／C++**：`code_test` 依序找 CMakeLists.txt 註冊的測試（`cmake` → 建置 → `ctest`）、Makefile（或 `makefile_test`）的 `test` 目標、或只有測試原始檔時直接用 g++ 編譯並連結 gtest。編譯失敗時列出整理過的「檔案:行號: error」與那一行原始碼，gtest 失敗列出期望值與實際值、跑到一半當掉的是哪個測試。`code_check` 用編譯器檢查改過的檔案（改標頭時編譯 include 它的原始檔）；括號改到不成對（輸出被截斷）的修改不會寫入。
- **工具鏈**（這台機器已經裝好、不需要 sudo）：pytest、cmake、ninja 在 `~/aiagent_venv_env/.venv`；GoogleTest 1.14 與 SQLite 在 `~/.local`，harness 執行指令時會把它們的路徑加進 `PATH`、`CPATH`、`LIBRARY_PATH`、`CMAKE_PREFIX_PATH`（所以 `g++ … -lgtest`、CMake 的 `find_package(GTest)` 直接可以用）。其他機器缺的話：`~/aiagent_venv_env/.venv/bin/pip install pytest cmake ninja`，GoogleTest 用 `sudo apt install -y libgtest-dev`（或從原始碼裝到 `~/.local`，見 [evals/devbench/README.md](evals/devbench/README.md)）。
- **ROS 2 的 colcon 工作區**（例如 `amr_base/src/<套件>`，ament_cmake 與 ament_python 混在一起）：每個檔案依所屬的套件（`package.xml`、有 `project()` 的 CMakeLists.txt）決定 include 目錄與依賴——`#include "my_pkg/x.hpp"` 對的是 `src/my_pkg/include`。**這台主機沒有 ROS 2**（ROS 2 在容器裡）時：用到 rclcpp 的 C++ 檔，`code_check` 會說明「缺 package.xml 宣告的外部依賴（或 msg、CMake 產生的這種建置時才有的標頭）、只檢查了結構，不是程式的錯誤」，不會報錯（專案自己的 `#include` 寫錯、真的編譯錯誤照樣抓）；`code_test` 每個套件分開跑——C++ 只編譯那個套件、跑不依賴 ROS 的 gtest，Python 在套件目錄跑 pytest（各套件同名的 `test_flake8.py` 不會互相衝突），需要 rclcpp／rclpy／ament_flake8 的測試檔跳過，並說明要在容器裡 `colcon test`。coding job 的驗證測試全部需要 ROS 2 時，那一項以靜態檢查為準，不會派 worker 去「修」沒錯的程式；`repo_map` 會列出工作區的套件與建置類型。要完整建置與測試，仍然要在 ROS 2 的環境 `colcon build`／`colcon test`。
- **`.gitignore`**：掃描（repo_map、code_search、code_refs、code_check、規劃的名稱索引）會略過 `.gitignore` 排除的**目錄**（建置產物、下載的第三方程式、`evals/results/` 這類），單一檔案不受影響；明確指定那個目錄時照樣會掃。
- **照規格文件做的任務**：任務裡提到工作區的文件（例如「照 docs/PRD.md、docs/architecture_design.md 實作」），規劃與每個 worker 都會拿到整份內容，驗證時會對照文件裡的函式簽名（參數個數），任務明確列出要建立的檔案時，計畫不會自己多加原始檔。

### 模型的選擇與實測（2026-10-08）

測試一律是真的 pytest／GoogleTest，用來計分的測試 agent 從頭到尾看不到（RTX 5090、Ollama，Isaac Sim 同時佔 7.7 GB 顯示記憶體）。

**自建情境**（`evals/run_coding_evals.py`：小專案，hidden tests 驗收）

| 情境組 | gemma4:e4b | gemma4:26b |
|---|---|---|
| Python 6 個（新增方法＋改行為、跨檔改名＋CLI、照使用範例的多檔功能、除錯不能改測試、照規格建新模組、5 個檔案的長任務） | 10/12（各 2 次）＋改名另外 2/2；加上 ROS 2 支援後回歸 **12/12**（2 次） | **6/6** |
| C／C++ 5 個（CMake＋gtest：介面加虛擬方法、新類別＋解析器、從症狀除錯；Makefile＋gtest 的 C：新增 API、除錯） | **10/10**（v1、v2 各一次）；加上 ROS 2 支援後回歸 **10/10**（2 次） | v2 **5/5**（v1 4/5：cpp_triangle 規劃失敗） |
| ROS 2 colcon 工作區 3 個（這台主機沒有 ROS 2；ament_cmake 套件：新函式＋gtest、從症狀除錯；ament_python 套件：新函式＋改 rclpy 的 node＋pytest） | 第一版 1/3（照任務的套件內路徑在工作區根目錄另建測試檔，見設計筆記 2.14 之二）→ 修正後 **9/9**（3 次） | **6/6**（修正前後各一次） |
| 主對話 14 個情境（harness 模式，含卡住偵測與宣稱完成偵測上線後的回歸） | **14/14** | — |

e4b 的兩次失敗都是模型錯誤（規劃把任務範例的 `export out.csv` 改成 `--output` 選項；把 `Inventory` 當成可迭代）。

**DevBench**（公開 benchmark，`evals/devbench/`：12 個 repo 各自從 PRD、UML、架構設計寫出整個專案，用官方的單元／驗收測試計分；v2＝加上 DevBench 找到的框架修正之後，見〈設計筆記 2.13〉。目前的程式另外多了 v3——整體驗證的修正讓通過的測試變少就還原到修正前——是在這些評測跑完之後才加的，用離線自我測試驗證過，下面的數字不含它）

| | e4b v1 | e4b v2 | 26b v1 | 26b v2 |
|---|---|---|---|---|
| 單元測試（共 116） | 22 | 9 | 14 | 11 |
| 驗收測試（共 51） | 0 | 8 | 18 | 11 |
| 依程式碼行數加權（單元／驗收，同論文的算法） | 14.8%／0% | 8.4%／20.6% | 12.3%／38.4% | 9.9%／20.0% |
| 12 個 repo 總時間 | 187 分鐘 | 141 分鐘 | 147 分鐘 | 89 分鐘 |

**對照：官方測試放在工作區**（`--visible-tests`，DevBench 基準 agent 的設定；26b v2）：單元 **84/116（72%）**、驗收 18/51（35%），依程式碼行數加權 67.4%／36.7%，12 個 repo 92 分鐘。看得到測試時，單元分數從一成多跳到七成（lice 0 → 21/25、logistic_system 0 → 17/17、graph-cpp 0 → 21/22），差距幾乎都是測試綁定的內部命名；端到端的驗收差不多。也就是說：**在已經有測試的專案裡（平常最常見的情況），這個框架＋26b 能把大部分的單元測試修到通過**；只給規格、沒有測試時，介面命名跟官方實作對不上是主要的失分。

- **單次的變異很大**：同一個模型、同一版程式，graph-cpp 一次驗收 5/5、一次 0/5；e4b 的 graph-cpp 一次單元 18/22、一次 0/22（DevBench 的文件自己不一致：UML 寫 `setVexer`、架構設計寫 `setVexes`，模型照哪一份取名，22 個單元測試就全過或全掛）。所以看兩次合計比較準：**e4b 單元 31/232（13%）、驗收 8/102（8%）；26b 單元 25/232（11%）、驗收 29/102（28%）**。
- **26b 在長任務的端到端（驗收測試）明顯較好**，約是 e4b 的 3.6 倍；C++ 的驗收尤其明顯（26b 合計 22/54，e4b 5/54）。
- **單元測試很依賴內部命名**：namespace（xlsx2csv 的測試寫死 `my_xlsx::xlsx_reader`，文件卻說不建 namespace 也可以）、模組常數（lice 的 `LICENSES`）、類別常數（stocktrends 的 `PERIOD_CLOSE`）、資料檔（geotext 的城市資料不在提供的檔案裡），所以兩個模型的單元分數都偏低；這部分多數是「規格沒寫清楚」，不是寫不出程式。
- 參考（DevEval README 的實作任務：22 個 repo、四種語言、依行數加權）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%。協定、agent、repo 都不同，**只能當量級參考**。

**建議**：coding job 用 **gemma4:26b**（規劃與 worker 都用；Coding 面板 ⚙️ 設定，或 `/code_model all gemma4:26b`）——自建情境兩個模型差不多，但長任務的完成度 26b 明顯較好，而且這台機器上 26b 不比 e4b 慢（MoE；DevBench v2 的 12 個 repo 26b 89 分鐘、e4b 141 分鐘）。主對話維持 e4b 也可以，但兩個模型加上 Isaac Sim 放不進 32 GB，主對話與 coding job 交替時 Ollama 要換模型（每次幾秒）；`WEB_CONSOLE_MODEL=gemma4:26b` 全部用 26b 就不會換。顯示記憶體吃緊的設備，e4b 做小範圍的修改（自建情境那種規模）仍然可靠。gemma4:31b 在 Ollama 上有（20.4 GB，dense），這次沒有下載測試；要試的話 `ollama pull gemma4:31b` 後在 ⚙️ 設定選它，再用 `evals/devbench/run.py --model gemma4:31b` 比較。

**注意**：自建情境同時被拿來找問題、修問題（改 prompt 與檢查規則的依據），全過偏樂觀；DevBench 的 12 個 repo 也被用來找框架的問題。比較改動前後，請固定版本、每個組合至少跑兩次。

## 目前狀態（2026-10）

- **可用**：原本 AI_agent_harness 的全部功能（CLI 與 Web Console、技能系統、兩種上下文模式、執行前關卡、Plan 模式、`/make_skill`、附圖分析、上下文壓縮、工具回傳存檔與 `result_recall`），加上 coding orchestrator、13 個程式開發技能、Web 的 Coding 面板、coding 評測（5 個情境，hidden tests 驗收）。
- **驗證方式**：`evals/coding_selftest.py`（離線、假模型：orchestrator 的流程與技能腳本的各種保證，含真的 pytest 與 gtest、任務清單的檔案、修正變差就還原、ROS 2 工作區，12 個情境）；`evals/main_selftest.py`（離線：主對話的卡住偵測、宣稱完成偵測、路徑建議，9 個情境）；`evals/web_ui_test.py`（無頭 Chrome 實際操作 Web 介面，6 個情境）；`evals/run_coding_evals.py`（真模型、Python／C／C++／ROS 2 fixture、hidden tests 驗收，14 個情境）；`evals/devbench/`（公開 benchmark，12 個 repo）；主對話的路由情境在 `evals/run_evals.py`（`coding_route_modify`、`coding_route_question`）。
- **主要限制**：小模型寫的測試有時寫錯或寫得太鬆（所以評測用 hidden tests 驗收）；計畫可能拆得不理想（核准前要看一下）；指令安全檢查是啟發式的。完整清單見〈[設計筆記與已知限制](doc/設計筆記與已知限制.md#6-已知限制)〉第 23 點起。

## 主對話的程式把關（2026-10-08，從 coding 框架移植）

coding worker 用過、確實有效的幾個做法，也套到一般（非 coding）任務的主對話上，CLI、Web、評測共用：

- **卡住偵測**：同一個回合裡，同樣的動作（技能＋參數）得到同樣的結果——第二次在工具回傳後面附「不要再重複、換個做法」，第三次加強提醒（明確要它換技能或參數、或直接回報），第四次（或同一個錯誤第四次）停下這一回合、顯示 ⛔ 交回給你，不會一直跑到 25 輪上限。（v4.1：原本第三次就停，評測發現會切斷模型自己換做法的機會，見 [benchmark_study](benchmark_study/README.md)。）
- **沒有執行卻宣稱做完**：這一回合一個工具都沒有執行，回覆卻說「已經重新啟動了／已建立…」，提醒 AI 一次（要做就實際執行、沒做就照實說），畫面上會出現 ⚠️。條件句、疑問句、否定句不算。
- **路徑找不到時列出相近的路徑**：`view_file`、`list_dir`、`change_dir`、`code_view` 找不到時，列出大小寫或拼字最接近、或同名在別的目錄的路徑（小模型最常錯的就是差一點的路徑）。
- **技能用錯時直接說該用哪個**：`docker_runcmd` 是在容器裡面執行指令，被拿來跑 `docker start／restart` 時，直接說明要用 `host_runcmd` 在主機上執行。

## 運作方式

![架構圖](doc/images/AI_agent_harness的說明.png)

1. 使用者下指令，主 session 每輪回一個 JSON `{thought, reply, action}`，harness **只看 `action`**，`reply` 裡的文字不會被執行。
2. `action` 填技能名稱 → 回傳該技能的規格文件（這一輪不執行）；填規格標明的腳本路徑 → 才真的執行。沒有「技能名稱 → 腳本」的對照表，模型一定要先讀規格。會改變實體狀態的動作（派工單、取消任務、建容器、容器內非唯讀的指令）執行前一律由程式請使用者確認，任何模式都一樣。
3. 每次執行的完整原文都存成 `#編號` 並顯示給使用者。回傳怎麼進主對話看上下文模式：
   - **harness**（預設）：超過 500 tokens 時交給一次性的獨立 session，依使用者的問題擷取重點；主對話只收到重點與下一步建議。
   - **claude_code**：原文直接進上下文，超過 3000 tokens 保留頭尾並標明省略的行號與存檔編號；要不要回存檔查、用什麼查，由模型自己決定。
4. 大量回傳會在 `logs/tool_results/tools_use_index.md` 留下一句話描述（整句保存、不截斷），附在 system prompt 尾端；Web 附圖的影像分析也存成 `#編號` 記進這裡（標〔附圖分析〕）。使用者之後（包括下次啟動）追問舊資料時，模型執行 `result_recall <編號>`，讓獨立 session 回到原文重新提煉；問題要一起看幾份時，一次給多個編號。
5. system prompt 只放不常變的內容（KV cache 才能重用）；工作目錄、目標容器、核准的計畫這些常變的小東西，每次接在送出內容的最後面。
6. 上下文超過水位時，舊對話會融合成一份滾動摘要；使用者的原話由程式逐字保留，被壓掉的對話也存成 `#編號`，需要時可以取回。對話片段的描述只講那一段談了什麼、決定了什麼，列在 system prompt 的「過去的對話片段」一節，跟工具回傳分開列、保留上限也分開算（編號共用同一個序列，取回一樣用 `result_recall`）。claude_code 模式會先把舊的工具回傳清成「原文在存檔」的佔位，不夠才摘要。

![一回合的狀態機](doc/images/AI_agent_harness的狀態轉移.png)

![工具回傳管線](doc/images/AI_agent_harness的工具回傳管線.png)

每一步對應到哪個函式、狀態存在哪裡、要改某件事該看哪裡，見〈[架構說明](doc/架構說明.md)〉。

## 快速開始

**需要**：已在執行的 [Ollama](https://ollama.com/)（先 `ollama pull gemma4:e4b`）、Python 3.10+ 與 `pip install ollama`。附圖功能需要 `Pillow`；容器與 ROS2 技能需要宿主機的 `docker` CLI；調度系統技能需要 fih_rmf_system 的 web_console（:8020），離線時可用 `skills_system/scripts/mock_server.py` 代替。

```bash
python3 web_console.py      # Web：http://127.0.0.1:8765（只綁本機）
python3 Agent_Runner.py     # CLI
```

Web 左欄是對話，右欄是系統與工具回傳：每次工具回傳有兩張卡，一張是完整原文（附 `#編號`，可點開），一張是「AI 實際收到的內容」。輸入框打 `/` 會跳出指令與技能選單，旁邊有附圖（📷）與 Plan 模式（📝）按鈕。

| 常用指令 | 作用 |
|---|---|
| `/auto on` | 工具結果自動加入、連續執行到做完（Web 最多 25 輪） |
| `/hybrid on` | 每次問要不要加入，不論選哪個都繼續推論（預設的 manual 也會問，但選「不加入」就結束） |
| `/plan on` | 下一個任務先由 AI 列步驟草稿，核准（y）後才執行；草稿由系統保存，AI 只會改你提到的那幾條 |
| `/plan add`、`/plan edit N`、`/plan del N`、`/plan move N M`、`/plan show` | 直接改計畫草稿（不經過 AI）；沒開 `/plan on` 也能自己一條條列 |
| `/plan_exec_guard on` | 計畫執行中：計畫外、會改變狀態的技能不執行，AI 停下來會自動提醒繼續，連續失敗 3 次退出計畫（預設關＝沒有限制） |
| `/context_mode harness`、`/context_mode claude_code` | 切換上下文模式（差別見〈[架構說明 1.1](doc/架構說明.md#11-兩種上下文模式context_mode-harnessclaude_code)〉） |
| `/guard on`、`/guard off` | 執行前確認的開關（預設開；關閉只限這次執行） |
| `/skill <名稱>`、`/skills` | 手動載入某技能的規格／列出所有技能 |
| `/summarize off` | 大量回傳只給成功／失敗，不摘要 |
| `/make_skill <名稱>`、`/trajectory` | 把做對的對話整理成流程技能的規格（步驟只呼叫既有技能，不產生腳本）／查看操作軌跡 |
| `/compress`、`/clear` | 手動壓縮上下文／清空對話 |
| `/menu`（Web） | 列出全部指令 |

| 常用設定（環境變數） | 預設 | 說明 |
|---|---|---|
| `WEB_CONSOLE_MODEL` | `gemma4:e4b` | Web 用的主模型（CLI 寫在 `main()`）；在標題列 🧠 設定過之後以畫面上的設定為準（`logs/model_settings.json`） |
| `AGENT_MAIN_THINK` | 關 | 主對話的 thinking 模式（Web：🧠 或 `/think main on`） |
| `WEB_CONSOLE_HOST`／`WEB_CONSOLE_PORT` | `127.0.0.1`／`8765` | Web 綁定位址 |
| `AGENT_NUM_CTX` | `32768` | context 上限；記憶體小的設備可調低 |
| `AGENT_CONTEXT_MODE` | `harness` | 啟動時的上下文模式（`harness`／`claude_code`） |
| `AGENT_GUARDED_SKILLS` | 派工單、取消、刪逾時任務、建容器、容器內指令 | 執行前要確認的技能（逗號分隔） |
| `AGENT_SUMMARY_MODEL` | 同主模型 | 獨立 session 用的模型（沒設定時跟著主對話的模型，在 🧠 換主模型時一起換） |
| `RMF_WEB_CONSOLE_URL` | `http://localhost:8020` | 調度系統的位址 |
| `VISION_MODEL` | `gemma4:e4b` | 附圖分析用的模型 |

其他門檻與保留上限見〈[架構說明 §10](doc/架構說明.md#10-常數與環境變數)〉。

## 技能一覽

| 分類 | 技能 |
|---|---|
| 程式開發 | `repo_map`、`code_view`、`code_search`、`code_refs`、`code_check`、`code_test`、`code_diff`、`code_job_send`、`code_job_status`、`code_job_cancel`（worker 專用：`code_edit`、`code_write`、`code_run`） |
| 檔案系統 | `list_dir`、`search_text`、`find_file`、`change_dir`、`view_file`、`code_ast_reader`、`host_runcmd`、`file_ops`、`csv_query` |
| 容器 | `docker_containers`、`docker_images`、`docker_est`、`docker_open`、`docker_runcmd`、`docker_ctl` |
| ROS2（容器內） | `ROS2_topic_list`、`ROS2_topic_echo`、`ROS2_node_list`、`ROS2_node_info`、`ROS2_param`、`ROS2_topic_pub` |
| 調度系統 | `workpackage_send`、`workpackage_status`、`workpackage_cancel`、`overpending_cancel`、`semantic_map`、`rmf_handshake` |
| 多步驟維運任務（v5） | `ops_run`（規劃 → 確認整份計畫 → 每一步派 worker、程式檢查） |
| 多模態 | `stt_engine`、`image_inspect` |
| 工具結果存檔 | `result_recall`、`result_grep`、`result_view`、`result_list` |
| 記憶 | `modify_memory` |

索引在 [`skills_system/SKILLS.md`](skills_system/SKILLS.md)，每個技能的規格在 `skills_system/tools/<name>.md`；各技能的參數與重點見〈[設計筆記 §3](doc/設計筆記與已知限制.md#3-技能清單全部功能)〉。

## 目錄結構

```
AI_agent_harness/
├── Agent_Runner.py     # CLI 入口（幾行，實作在 agent_core/）
├── web_console.py      # Web 入口（幾行，實作在 web_app/）
├── agent_core/         # 核心：SkillAgent（由各 mixin 組成）、回覆協議、常數、CLI——唯一的核心邏輯來源
├── web_app/            # Web 介面（純標準庫）：狀態、回合流程、slash 指令、HTTP、static/index.html
├── AGENT.md            # system prompt 主體：角色、JSON 回覆格式、執行協議、安全原則、記憶協議
├── coding_agents/      # coding worker 與規劃 session 的 system prompt（worker.md、planner.md，可以直接改）
├── context_modes/      # 兩種上下文模式各自的規則（harness.md、claude_code.md），接在 AGENT.md 後面
├── Memory.md           # 全域長期記憶（每輪常駐）
├── skills_system/
│   ├── SKILLS.md       # 技能索引（常駐 system prompt）
│   ├── tools/          # 各技能的規格文件（按需載入）
│   └── scripts/        # 各技能實際執行的腳本與共用模組
├── vision/             # 多模態影像 library（擷取、推論、前端框選）
├── subagent/           # 獨立的框選截圖 → 視覺推論小工具
├── evals/              # 評測：主對話（run_evals.py、scenarios.py、main_selftest.py）、coding（run_coding_evals.py、coding_scenarios.py、
│                       #   coding_fixtures/：Python、C++（CMake）、C（Makefile））、Web 介面（web_ui_test.py）、DevBench（devbench/）
├── doc/                # 架構說明、設計筆記、圖（.puml 與產生器）
└── logs/               # 執行時產生：工具回傳存檔、檢索清單、軌跡、摘要歸檔、模型呼叫耗時、coding_jobs/（.gitignore）
```

## 未來規劃的注意事項

接下來的方向是**執行設計好的技能與固定技能組**，而不是 coding 那種開放式任務：調度系統上的人機交握，以及引入心跳機制後的定時狀況回報、定期執行某些技能。心跳機制的起因是：未來會有來自不同地方的 VLM 語意資訊（例如各處攝影機的影像分析結果），需要 AI agent 分析、彙整之後才能回報，所以不是單純的定時腳本。設計時要注意：

- **模型選擇要在目標設備上量過再決定**：在 RTX 5090 上 gemma4:26b 兩種上下文模式都比 e4b 好、甚至略快（〈[設計筆記 2.11](doc/設計筆記與已知限制.md)〉與 `evals/results/`），但 26b 在弱設備上的主要代價是**讀 prompt**，不是產出：這次讀 prompt 就慢了 3 倍，而 system prompt 常駐約 5～8K tokens。另外 26b 模型本身 18 GB、e4b 9.6 GB，裝得下是前提。在目標設備上用 `evals/run_evals.py --model …` 與 `evals/perf_report.py` 實際量過才準；設備較弱時，e4b 搭配 harness 模式的時間與推論成本優勢比較大。
- **定時任務不一定要經過模型**：「定期執行某些技能」的步驟如果是固定的，排程直接執行腳本最穩、最省（`/make_skill` 產生的流程技能要由模型照步驟做，適合有人在場、要確認的流程；固定的多步驟要不經過模型，就寫成一支腳本）。模型只負責解讀結果、判斷異常、彙整多個來源（包括 VLM 的語意資訊）、寫報告，推論成本和出錯機會都會少很多。
- **心跳機制要注意上下文會越積越多**：長時間定時執行，每次都接在同一段對話後面，上下文會一直變長、壓縮一直觸發。建議每次心跳開一個乾淨的 session，只帶上次的結論（加上這次收到的 VLM 資訊與技能結果）。
- **無人值守時，執行前確認怎麼辦**：定時執行沒有人按「同意」。要事先決定：定時任務只准唯讀技能，或者給一份事先核准過的白名單。這一點現在的設計還沒處理（`guard.py` 目前一律要人確認）。
- **人機交握的時間限制**：現場等回應通常有時限，要把每個動作的延遲算進去。harness 模式大量回傳時會多一次獨立 session，在弱設備上可能要好幾秒。

## 文件

- 〈[架構說明](doc/架構說明.md)〉：`agent_core/` 與 `web_app/` 的完整解析，含每個模組負責什麼（先從第 0 節「工具回傳什麼時候會被摘要」看起）
- 〈[設計筆記與已知限制](doc/設計筆記與已知限制.md)〉：各機制的理由與實測數據、完整技能清單、驗證方法、已知限制、未來方向
- 〈[長期願景](doc/長期願景.md)〉：AGV/AMR 車隊調度場景的構想（尚未實作）
- 〈[評測](evals/README.md)〉：怎麼跑、情境清單、怎麼加情境、怎麼讀報表
- 〈[benchmark_study](benchmark_study/README.md)〉：2026-10 的完整評測——《評估報告》（結論、使用建議、改進路線圖）、《技術報告》（方法、全部結果與統計）、用到的資料集、參考文獻（論文 PDF）、原始紀錄與分析程式
- 〈[benchmark_study_3](benchmark_study_3/README.md)〉：第三次評測（2026-10-10）——小而有測試的專案（寫測試＋覆蓋率、修多個 bug、補回跨檔功能、Aider polyglot，Python／C++ 62 題）與非編碼的維運任務（目錄與文件、Docker、ROS 2、調度交握、複合任務：50 個情境＋20 個保留情境，在隔離的 Docker-in-Docker 沙盒裡真的執行）；v5 的改動：覆蓋率、只寫測試的工作、回歸檢查、非編碼的 orchestrator（ops_run）與維運技能
- 〈[benchmark_study_2](benchmark_study_2/README.md)〉：第二次評測（2026-10-09）——既有專案（SWE-bench 子集 24 題，Python／C／C++，在官方 Docker 環境裡跑）、模型組合（DeepSeek-R1 規劃＋Qwen2.5-Coder worker）、thinking 模式的實測、規劃階段 self-refine 的評估；評測中找到並修正的問題（C++ 掃描器的災難性回溯：v4.1.1；大型檔案的修改視窗、既有專案的測試指令與範圍、改動要小、減少空轉：v4.2）
- 圖的來源在 `doc/*.puml`，用 `python3 doc/流程圖產生器.py` 重新產生
