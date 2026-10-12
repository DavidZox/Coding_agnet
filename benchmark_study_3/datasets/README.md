# 第三次評測的資料集

兩組任務，對應這次的兩個方向：

| 資料集 | 內容 | 題數 | 語言／領域 |
|---|---|---|---|
| [`small_projects/`](small_projects/) | 小而有測試的專案（2～14 個正式程式檔）：寫測試＋覆蓋率（TW）、修多個 bug（BF）、補回跨檔功能（FE）、單檔練習題（AP） | 62 | Python 37、C++ 25 |
| [`ops_suite/`](ops_suite/) | 非編碼的維運任務：目錄與文件、Docker、ROS 2、調度系統的交握、跨領域的複合任務（在隔離的沙盒裡真的執行） | 50＋保留組 20 | — |

`source/` 是兩個上游資料集的原始 clone（只用來產生任務，評測時不讀）。

## small_projects：小而有測試的專案

每一題＝一個工作區範本（`workspaces/<題目>/`）＋任務說明（`tasks/<題目>.json` 的 `task`，寫法像使用者交代工作）＋計分方式。

| 類別 | 題數 | 來源 | 任務 | 計分（`tools/score.py`） |
|---|---|---|---|---|
| **TW**（write tests） | 18：DevBench 12（Python 7、C++ 5）＋ProjectTest 6（Python） | 參考實作，**拿掉全部的單元測試** | 幫專案寫單元測試、量覆蓋率、回報還沒涵蓋的部分；不能改正式程式 | 測試在原本的程式上要通過；正式程式的**行／分支覆蓋率**（Python：coverage.py；C++：gcov＋gcovr）；**突變分數**（把正式程式改壞一處，測試抓不抓得到）；有沒有改正式程式、沒有斷言的測試 |
| **BF**（bug fix） | 12（DevBench：Python 7、C++ 5） | 參考實作植入 3 個 bug（突變），每個都讓官方單元測試失敗；分散在 1～3 個檔案（7 題跨 2 個以上的檔案） | 照失敗的測試名稱找出原因並修正（測試是對的，不能改） | 官方的**單元＋驗收測試全部通過**才算解決；另記有沒有改到測試 |
| **FE**（feature） | 12（DevBench：Python 7、C++ 5） | 參考實作拿掉一個跨 2～5 個檔案的功能（連同那個功能的單元測試） | 照需求說明補回功能、並補單元測試 | 官方的單元＋驗收測試全部通過；另記測試有沒有被改壞 |
| **AP**（Aider polyglot） | 20（Python 10、C++ 10） | Exercism 練習題（Aider 的 polyglot benchmark） | 只有說明與骨架，照說明實作（單檔，**只當能力對照**，不是這次的重點） | 官方測試全部通過 |

- **突變體**（`mutants/*.json`）：TW 的分母只用「官方測試抓得到」的突變體（DevBench）；ProjectTest 沒有官方測試，用全部有效的突變體（每題 60 個，絕對分數，只在同一題內比較版本）。
  每個突變體記下節點（Python AST）或 token（C++）的編號，計分時套到同一個位置。`score.py verify --fix` 用參考解的測試跑一次計分程序，
  抓不到的（建立時偶發的當掉／逾時）標成 `unstable`、不計分（目前只有 xlsx2csv#m22）。
- **驗證**：`python3 tools/score.py verify`——用參考實作／官方測試跑每一題的計分，TW 要 100% 突變分數、BF／FE 要全部通過：56/56（ProjectTest 的 6 題沒有參考測試，不在這個驗證裡）。
- **重建**：`tools/build_devbench.py`（TW、BF）、`tools/build_fe.py`（FE，規格在 `fe_specs.json`）、`tools/build_projecttest.py`、`tools/build_aider.py`。
  DevBench 的資料來自第一次研究準備的資料（`evals/devbench/prepare.py`）。
- 每題的大小（正式程式檔數／行數）在技術報告的附錄；xlsx2csv 有 1.4 萬行是因為附帶了解壓縮的程式庫，要測的只有 4 個檔案。

## ops_suite：非編碼的維運任務

| 領域 | 主要組 | 保留組 | 例子 |
|---|---|---|---|
| 目錄與文件（fs） | 12 | 4 | 找設定值在哪個檔案、統計 log、比對設定檔、改一個參數、整理 CSV 寫成報告、搬資料夾、用範本建資料夾 |
| Docker | 10 | 4 | 容器總覽與結束碼、看 log 找錯誤、容器裡的設定與環境變數、診斷為什麼停了、建／停／重啟容器 |
| ROS 2 | 10 | 4 | node／topic、電量、執行中的參數、domain 不同看不到 topic、頻率、對 topic 回 handshake yes |
| 調度交握（handshake） | 10 | 4 | 派工單並追到完成、診斷卡住（機器人回 no／沒回應／離線）、補發遺失的完成訊號、取消、OverPending |
| 複合任務（complex） | 8 | 4 | 處理卡住的工作包並寫紀錄、交班報告、重啟並驗證再記錄、改派、照 CSV 批次派工、改設定再派工 |

- **沙盒**（`sandbox/`）：一個 Docker-in-Docker daemon（`docker:27-dind`，port 23750）——agent 的 docker 技能透過 `DOCKER_HOST` 只看得到這個 daemon，
  碰不到主機上真的容器；裡面是 5 個一般容器（web_cache、log_writer、nav2_test、db_backup、scratch_tools）與 `rmf_sim`。
  **rmf_sim** 是依 `fih_rmf_system` 的行為寫的模擬（ROS 2 Jazzy＋`fih_rmf_msgs`）：distribute 每 0.5 秒授權、逾時進 OverPending、task_exec_fin、
  web_console 的 HTTP API（派工、查狀態、取消）與 manual_trigger（手動回 yes／no、補發完成訊號）；機器人的行為可以設定
  （正常、忙碌回 no、不回應、遺失完成訊號、離線、走得慢）。檔案沙盒（`fs_world.py`）是固定內容的維運工作目錄（設定、log、CSV、文件、範本）。
- **計分**（`checks.py`）：看最後的狀態（檔案快照、容器狀態、rmf_sim 的事件紀錄與工作包狀態），加上回覆裡要出現的事實（字串或正規表示式）；
  **禁止動作**（動了沒交代的容器、取消了不該取消的工作包、改了不該改的檔案…）發生任何一個就算失敗。答案都由沙盒的內容事先算好。
- **保留組**（`scenarios_holdout.py`）：開發 v5 時看過主要組的失敗紀錄、也拿來調整提示與技能，所以 v5 在主要組的分數會偏樂觀。
  保留組在 v5 調整之前寫好、之後不拿來調整，用來看改進能不能推廣到沒看過的說法與任務。
- **驗證**：`python3 reference.py --set all`——每個情境的參考解法（直接操作沙盒，不經過模型）都拿滿分（70/70）；
  `--null`（什麼都不做、只回一句不知道）每一個都不及格（70/70），檢查不是白送的。

## 來源與授權

| 來源 | 用在 | 授權 | 版本 |
|---|---|---|---|
| DevBench（open-compass/DevEval）[Li et al. 2024] | TW 12、BF 12、FE 12 | 資料 CC BY 4.0、程式 Apache 2.0 | commit `bb593c1f`（第一次研究準備的子集，見 `../../benchmark_study/datasets/devbench_subset/SOURCE.md`） |
| ProjectTest（YiboWANG214/ProjectTest）[Wang et al. 2025] | TW 6 | MIT | commit `a893144b`（`source/ProjectTest/`） |
| Aider polyglot benchmark（Aider-AI/polyglot-benchmark），內容來自 Exercism 的 Python、C++ track | AP 20 | Exercism 各 track 為 MIT | commit `7e0611e7`（`source/polyglot-benchmark/`） |
| `fih_rmf_msgs`（使用者的 `amr_base` 工作區） | rmf_sim 的訊息定義 | 內部 | 複製到 `ops_suite/sandbox/rmf_sim/fih_rmf_msgs/`，只用在沙盒 |
| ops_suite 的情境、檔案沙盒、rmf_sim | 非編碼評測 | 這次自己寫的 | — |

`source/` 裡的 clone 是上游的完整內容（ProjectTest 含作者用各種 LLM 產生的測試，約 165 MB）；要對外分享時只留任務用到的部分並保留授權檔。
