"""DispatchMixin：技能載入與派發——兩階段揭露（技能名稱回規格、腳本路徑才執行）、run_tool、_exec_script。"""
import os
import shlex
import subprocess
import sys
from .config import SKILL_DOC_PREFIX, SKILL_LOADED_MARKER, TOOL_EXEC_TIMEOUT, WORKFLOWS_ENABLED

from .protocol import action_text, doc_type, is_procedure_doc, parse_agent_reply

# 流程技能（/make_skill 依對話整理的規格，沒有自己的腳本）載入後，下一步怎麼做：照步驟一步一步來
PROCEDURE_NEXT_STEP = ("這是流程技能，沒有自己的腳本：照規格的「步驟」從第 1 步開始，一輪只做一步——要執行的步驟，"
                       "action.command 填該步寫的腳本路徑（scripts/...）、args 照該步填（{名稱} 換成實際的值）；"
                       "要向使用者確認或詢問的步驟，在 reply 問、action 填 null，等使用者回答再做下一步；"
                       "檢查、告知的步驟依前面步驟的回傳做。")


# 腳本輸出最後幾行的狀態標記（見 _trailing_markers；規範見 doc/技能撰寫規範.md）：跟腳本共用同一份清單（_shell_common.protect_tail 也用它）
from skills_system.scripts._shell_common import STATE_MARKERS  # noqa: E402

# 任務引擎（agent_core/task_engine.py）：在 _run_tool_once 裡攔下、交給 TaskMixin
TASK_PSEUDO_SCRIPTS = ("task_run_cmd.py",)
# 數據分析（agent_core/analysis_job.py，全部由程式做）：同上，交給 AnalysisMixin
ANALYSIS_PSEUDO_SCRIPTS = ("analysis_run_cmd.py",)
# 工作流（agent_core/workflow.py）：同上，交給 WorkflowMixin
WORKFLOW_PSEUDO_SCRIPTS = ("workflow_run_cmd.py",)


def workflow_next_step(name, doc):
    """模型用工作流的名稱當技能載入時：說明要用 workflow_run 執行（需要的資訊照規格的「需要的資訊」）。"""
    need = []
    for ln in doc.splitlines():
        ln = ln.strip()
        if ln.startswith("* `{") and "}`" in ln:
            key = ln[4:ln.index("}`")]
            need.append(f"{key}=<值>" + ("（選填）" if "選填" in ln else ""))
    return (f"這是工作流（程式照步驟做，不是一個技能）：下一輪 action.command 填 scripts/workflow_run_cmd.py、args 填「{name} "
            f"{' '.join(need)}」（值從使用者的話取得，拿不到的先問使用者），不要自己照步驟一個技能一個技能做；"
            f"會改變狀態的步驟系統會在開始時請使用者確認，不用先問。")


class DispatchMixin:

    def list_skills(self):
        """解析 SKILLS.md 索引：每個技能的名稱、一行描述、所屬分類（## 標題）。
        只列出 tools/<name>.md 真的存在的技能。Web Console 的「/」選單與 CLI 的 /skills 都用這個。"""
        skills = []
        category = "其他"
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return skills
        for line in lines:
            if line.startswith("## "):
                category = line[3:].strip()
                continue
            if not line.startswith("- ["):
                continue
            name = line[3:line.index("]")] if "]" in line else ""
            if not name or not os.path.exists(os.path.join(self.tools_dir, f"{name}.md")):
                continue
            desc = line.split("—", 1)[1].strip() if "—" in line else ""
            skills.append({"name": name, "description": desc, "category": category})
        return skills

    def manual_skill_block(self, skill_name):
        """使用者手動按需載入技能規格時，要附在下一則使用者訊息後面的區塊。
        內容等同 AI 自己 EXECUTE 技能名稱後系統回傳的規格，讓 AI 可以直接依其中的腳本路徑執行、
        省掉一輪「先載規格」。技能不存在回傳 None。"""
        doc = self._load_skill_doc(skill_name)
        if doc is None:
            return None
        name = skill_name[:-3] if skill_name.endswith(".md") else skill_name
        how = (PROCEDURE_NEXT_STEP if is_procedure_doc(doc)
               else "依此內容才可執行：action.command 填其中標明的實際腳本路徑、args 填參數")
        return (
            f"{SKILL_LOADED_MARKER}\n"
            f"{SKILL_DOC_PREFIX} '{name}' 的規格文件（使用者從選單手動載入，等同你以 action.command 填技能名稱後"
            f"系統回傳的規格；{how}）：\n{doc.rstrip()}"
        )

    def _load_skill_doc(self, skill_name):
        """若 skill_name 對應到 tools/<skill_name>.md，回傳其內容；否則回傳 None。
        容忍 AI 直接照抄索引連結而帶上 .md 後綴（例如 list_dir.md）。"""
        if skill_name.endswith(".md"):
            skill_name = skill_name[:-3]
        doc_path = os.path.join(self.tools_dir, f"{skill_name}.md")
        if not os.path.exists(doc_path):
            wf_path = os.path.join(self.base_path, "workflows", f"{skill_name}.md")   # 工作流：模型直接用它的名稱當技能
            if WORKFLOWS_ENABLED and os.path.exists(wf_path) and not skill_name.startswith("_"):
                with open(wf_path, "r", encoding="utf-8") as f:
                    return f.read()
            return None
        with open(doc_path, "r", encoding="utf-8") as f:
            return f.read()

    def _normalize_script_name(self, raw_token):
        """確保腳本檔名以 _cmd.py 結尾（例如 cd -> cd_cmd.py，find_file.py -> find_file_cmd.py）。"""
        if not raw_token.endswith("_cmd.py") and not raw_token.endswith(".py"):
            return f"{raw_token}_cmd.py"
        if raw_token.endswith(".py") and not raw_token.endswith("_cmd.py"):
            return raw_token.replace(".py", "_cmd.py")
        return raw_token

    def _parse_script_args(self, script_name, remainder):
        """把 action.args 字串以 shlex 依空白／引號拆成參數列表（含空白的參數用雙引號包住）。
        空字串參數（模型常寫成 `. ""`）一律丟掉：沒有任何腳本需要空的位置參數，留著只會變成 [ERROR] 找不到路徑。"""
        try:
            parts = shlex.split(remainder)
        except Exception:   # 引號不成對（實測模型會送 """）：退回空白切分並去掉殘留的引號
            parts = [a.strip("\"'") for a in remainder.split()]
        return [a for a in parts if a != ""]

    
    @staticmethod
    def _trailing_markers(output_text):
        """輸出最後連續的狀態標記行（[CWD_CHANGED]、[TARGET_CONTAINER]、[ANALYSIS_DATA]、[ROS2_WORKSPACE]、[CONTAINER_CWD] 與它下一行的路徑）。
        只認最後這一段：原文（容器的 log、指令的輸出）裡剛好出現同樣的字，不會被當成標記改掉 harness 的狀態。"""
        lines = output_text.rstrip().splitlines()
        j = len(lines) - 1
        while j >= 0:
            ln = lines[j].strip()
            if ln.startswith(STATE_MARKERS) or (j >= 1 and lines[j - 1].strip().startswith("[CONTAINER_CWD]") and ln.startswith("/")):
                j -= 1
                continue
            break
        return lines[j + 1:]

    def _sync_state_from_tool_output(self, output_text):
        """解析工具輸出最後的狀態標記（_trailing_markers），同步工作目錄、容器目錄、目前的數據、目標容器與 ROS 2 Workspace。"""
        import json

        lines = self._trailing_markers(output_text)

        for i, line in enumerate(lines):
            if line.startswith("[CWD_CHANGED]"):
                self.current_cwd = line.replace(
                    "[CWD_CHANGED]", ""
                ).strip()

            # 抓取 [CONTAINER_CWD] 標記的下一行作為路徑
            if line.startswith("[CONTAINER_CWD]") and i + 1 < len(lines):
                self.container_cwd = lines[i + 1].strip()

            # 目前分析的數據（ROS 2 數據技能成功操作某份數據後印的末行標記，比照目標容器）
            if line.startswith("[ANALYSIS_DATA]"):
                path = line[len("[ANALYSIS_DATA]"):].strip()
                if path:
                    self.analysis_data = path

            # 目標容器：沿用既有狀態同步機制
            if line.startswith("[TARGET_CONTAINER]"):
                self.target_container = line[
                    len("[TARGET_CONTAINER]"):
                ].strip()

            # ROS 2 Workspace：
            # [ROS2_WORKSPACE] {"container":"容器名稱","path":"/workspace/project"}
            if line.startswith("[ROS2_WORKSPACE]"):
                raw = line[len("[ROS2_WORKSPACE]"):].strip()

                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    # 不接受格式錯誤的狀態標記
                    continue

                container = str(data.get("container", "")).strip()
                workspace = str(data.get("path", "")).strip()

                # 只接受具有完整容器名稱及絕對路徑的狀態
                if (
                    container
                    and workspace.startswith("/")
                    and "\n" not in workspace
                    and "\r" not in workspace
                ):
                    self.current_ros2_workspace = {
                        "container": container,
                        "path": workspace,
                    }

    def run_tool(self, ai_response, approved=False):
        """執行 AI 回覆的 action（見 _run_tool_once），再交給 note_tool_result 做卡住偵測：同一個回合裡同樣的動作得到同樣的
        結果，第二次在回傳後面附提醒、第三次設 self.stuck（回合迴圈看到就停下來，見 turn_guard.py）。"""
        parsed = ai_response if isinstance(ai_response, dict) else parse_agent_reply(ai_response)
        return self.note_tool_result(parsed, self._run_tool_once(parsed, approved))

    def _run_tool_once(self, ai_response, approved=False):
        """依 AI 回覆 JSON 的 action 欄位執行（ai_response 可以是原始 JSON 字串或 parse_reply 的結果）。
        action 為 null／回覆不是合法 JSON → 不執行、回傳 None；reply 裡的文字完全不看。
        有 action 時行為分兩種：

        1. 若 command 對應到 tools/<name>.md 的技能規格文件（代表 AI 用的是
           SKILLS.md 索引裡的技能名稱），直接把規格文件內容當作系統回傳注入
           上下文，不執行任何腳本——這就是按需載入 (Progressive Disclosure)。
           不做技能名稱 -> 腳本檔名的猜測或對照；AI 讀完規格後，下一輪需改用
           規格書中標明的實際腳本路徑（例如 scripts/cd_cmd.py）才會真正執行。
        2. 否則將 command 視為實際腳本路徑，以 args 為參數執行對應的 CLI 腳本並回傳結果。

        執行前關卡：會改變狀態的技能（guard_check）沒有 approved=True 就不執行，回 [DENIED]。CLI／Web 先用
        guard_check 問使用者，同意後才以 approved=True 呼叫；其他呼叫端漏接確認時這裡也擋得住。
        """
        parsed = ai_response if isinstance(ai_response, dict) else parse_agent_reply(ai_response)
        action = parsed.get("action")
        self.last_result_id = self.last_result_file = None   # 只有真的執行腳本（_record_trajectory）才會有存檔
        if not action:
            return None

        try:
            payload = action_text(action)
            parts = payload.split(maxsplit=1)
            raw_token = os.path.basename(parts[0])
            remainder = parts[1] if len(parts) > 1 else ""

            skill_doc = self._load_skill_doc(raw_token)
            if skill_doc is not None and doc_type(skill_doc) == "Workflow":
                name = raw_token[:-3] if raw_token.endswith(".md") else raw_token
                print(f"📖 Agent 選擇工作流: {name}（載入工作流的規格，尚未執行）")
                return (f"{SKILL_DOC_PREFIX} '{name}' 的規格文件（由系統提供）。這一輪只是載入規格、還沒有執行任何東西："
                        f"{workflow_next_step(name, skill_doc)}\n{skill_doc}")
            if skill_doc is not None:
                procedure = is_procedure_doc(skill_doc)
                print(f"📖 Agent 選擇技能索引: {raw_token}（載入{'流程技能的' if procedure else ''}規格文件，尚未執行）")
                # 回給模型的這段話是兩階段流程裡最關鍵的一句：實測 JSON 協議下小模型載完規格容易停下來解釋規格或
                # 反問使用者（reply 欄位本身就在邀請它聊天），所以這裡直接下達下一輪該做的事。帶了參數時再明說那些參數
                # 沒有被執行——實測模型用「docker_open <容器>」載完規格就當作容器已切換，直接做下一步。
                # 實測（2026-09-25 情境稽核）：只寫「繼續使用者原本的任務」時，模型會跳過這一步直接做下一步（載完 change_dir
                # 規格就去 ls），所以要明說「下一輪先把這一個技能真正執行一次，之後才做下一步」。
                if procedure:
                    next_step = (f"你附的參數「{remainder.strip()}」沒有被執行。" if remainder.strip() else "") + PROCEDURE_NEXT_STEP
                elif remainder.strip():
                    next_step = (f"你附的參數「{remainder.strip()}」也沒有被執行、狀態沒有改變。下一輪請先把這個技能真正執行一次："
                                 f"action.command 填規格標明的實際腳本路徑（scripts/...）、args 填同樣的參數，執行完看到結果後才做下一步；")
                else:
                    next_step = ("下一輪請先把這個技能真正執行一次——action.command 填規格標明的實際腳本路徑（scripts/...）、"
                                 "args 填參數，執行完看到結果後才做使用者任務的下一步；")
                return (f"{SKILL_DOC_PREFIX} '{raw_token}' 的規格文件（由系統提供）。這一輪只是載入規格、還沒有執行任何東西：{next_step}"
                        f"不要向使用者解釋規格內容，也不要詢問是否要執行。\n{skill_doc}")

            script_name = self._normalize_script_name(raw_token)
            if script_name == "result_recall_cmd.py":
                # 偽技能：result_recall 沒有實體 scripts/result_recall_cmd.py（要呼叫 ollama.chat，只能在本
                # process 內做；核心邏輯都在 agent_core，見 doc/架構說明.md），必須在存在性檢查前攔截，
                # 否則會落入下面「找不到腳本」的分支。規格文件走一般的兩階段揭露，不受影響。
                return self._result_recall(remainder)
            script_path = os.path.join(self.base_path, "scripts", script_name)

            print(f"🛠️  Agent 啟動工具: {script_name}")
            if not os.path.exists(script_path):
                # 幾乎都是模型跳過「先載入規格」直接猜腳本檔名（例如 list_dir_cmd.py，實際是 ls_cmd.py）。
                # 給可直接行動的指引：猜的名稱裡若含有某個技能名稱，就建議先 EXECUTE 那個技能取得規格。
                stem = script_name[:-len("_cmd.py")] if script_name.endswith("_cmd.py") else script_name
                candidates = [
                    f[:-3] for f in sorted(os.listdir(self.tools_dir))
                    if f.endswith(".md") and (f[:-3] in stem or stem in f[:-3])
                ] if os.path.isdir(self.tools_dir) else []
                if candidates:
                    return (f"[ERROR] 找不到腳本 {script_name}。這個名稱看起來是技能 {', '.join(candidates)}，請先把 action.command "
                            f"填成 `{candidates[0]}`（args 留空）載入規格文件，再依規格標明的實際腳本路徑執行。")
                if "/" not in parts[0] and not raw_token.endswith(".py"):
                    # 填的是技能名稱、但沒有這個技能：多半是舊摘要、舊對話或記憶裡提到、後來移除的技能（實測：plan_task
                    # 移除後，模型照舊摘要去叫它）。明說不存在，不要讓它以為只是少載了規格、再去猜腳本檔名。
                    return (f"[ERROR] 沒有 `{raw_token}` 這個技能（SKILLS.md 與 skills_system/tools/ 都沒有）。它可能是舊摘要、"
                            f"舊對話或記憶裡提到、但已經移除的名稱：不要再使用，也不要猜腳本檔名；改用 SKILLS.md 列出的技能完成"
                            f"使用者的任務，沒有適合的技能就直接告訴使用者目前沒有這個功能。")
                return (f"[ERROR] 找不到腳本 {script_name}。腳本路徑只能從規格文件取得，不可自行推測："
                        f"請先以 action.command 填入 SKILLS.md 裡的技能名稱載入規格。")

            if not approved:
                guard = self.guard_check(parsed)
                if guard:
                    print(f"🛡️ {guard['skill']} 需要使用者確認才能執行，這次沒有執行。")
                    return self.guard_blocked_text(guard)
            clean_args = self._parse_script_args(script_name, remainder)
            # 軌跡記錄用：執行「前」的狀態
            cwd_before, container_before, target_before = self.current_cwd, self.container_cwd, self.target_container
            if script_name in TASK_PSEUDO_SCRIPTS:
                # 偽技能（同 result_recall）：規劃與執行要呼叫模型，在本 process 內做（agent_core/task_engine.py）；腳本檔只是讓
                # 存在性檢查與確認關卡（task_run）照常運作，所以攔在關卡之後。記一筆軌跡：報告有存檔編號，之後可以 result_recall；
                # 每一步 worker 的工具輸出也各自記軌跡（#編號，報告裡的事實引用它們）
                output_text = self.task_run(remainder)
                self._record_trajectory(script_name, clean_args, output_text, cwd_before, container_before, target_before)
                return output_text
            if script_name in WORKFLOW_PSEUDO_SCRIPTS:
                # 偽技能：工作流由程式照步驟推進（agent_core/workflow.py），判斷點要呼叫模型；每一步的輸出各自記軌跡（#編號），
                # 整份報告也記一筆
                output_text = (self.workflow_run(remainder) if WORKFLOWS_ENABLED else
                               "[ERROR] 這個環境關閉了工作流（AGENT_WORKFLOWS=0）：用技能一步一步做，或用 task_run。")
                self._record_trajectory(script_name, clean_args, output_text, cwd_before, container_before, target_before)
                return output_text
            if script_name in ANALYSIS_PSEUDO_SCRIPTS:
                # 偽技能：在本 process 內做（agent_core/analysis_job.py：job 資料夾、進度推到 Web 右欄、目前的數據同步）；
                # 報告記一筆軌跡並存檔（#編號），之後可以 result_recall
                output_text = self.analysis_run(remainder)
                self._record_trajectory(script_name, clean_args, output_text, cwd_before, container_before, target_before)
                return output_text
            self._raw_args = remainder          # 原始的參數字串（file_ops 的內容含引號時，shlex 拆過的參數會壞掉）
            try:
                output_text = self._exec_script(script_name, script_path, clean_args)
            finally:
                self._raw_args = ""
            self._sync_state_from_tool_output(output_text)  # 逾時訊息裡不會有狀態標記，掃過去是安全的 no-op
            self._record_trajectory(script_name, clean_args, output_text, cwd_before, container_before, target_before)
            return output_text

        except Exception as e:   # noqa: BLE001  偽技能（ops／analysis）或 harness 自己的錯：照實回報，[ERROR] 開頭才會被當成失敗
            return (f"[ERROR] 執行時發生未預期的錯誤（{type(e).__name__}: {e}）。下一步：確認參數（引號要成對）後重試一次；"
                    f"同樣的錯誤再出現就把這段訊息告訴使用者，不要一直重試。")

    def _usable_cwd(self):
        """目前的工作目錄還能用（存在、可以讀與進入）就回 None；不能用（被刪掉、切到沒有權限的目錄）就換回專案目錄，回傳說明。
        以前切到 /root 之後每一支腳本都因為 cwd 失敗、連 change_dir 都跑不了，只能重開程式。"""
        cwd = self.current_cwd
        if cwd and os.path.isdir(cwd) and os.access(cwd, os.R_OK | os.X_OK):
            return None
        self.current_cwd = self.script_dir
        return (f"[ERROR] 目前的工作目錄 {cwd} 已經不存在或沒有權限，系統已把工作目錄換回 {self.script_dir}，這一次沒有執行。"
                f"下一步：用 change_dir 切到要的目錄（要有讀取權限），再執行一次。")

    def _exec_script(self, script_name, script_path, clean_args, extra_env=None):
        """執行一支腳本、回傳 output_text；不記軌跡、不同步狀態（呼叫端負責）。不讀標準輸入（腳本若等人輸入會直接讀到結尾，不會卡住）；
        extra_env 是額外的環境變數。工作目錄不能用時不執行、回 [ERROR]（_usable_cwd）。"""
        bad_cwd = self._usable_cwd()
        if bad_cwd:
            return bad_cwd
        env = os.environ.copy()
        env["CONTAINER_CWD"] = self.container_cwd
        env["TARGET_CONTAINER"] = self.target_container  # 容器技能省略容器名稱時的預設（比照 cwd）
        env["TOOL_RESULTS_DIR"] = self.results_dir()     # result_list／result_grep／result_view 的存檔目錄
        env["HARNESS_SESSION"] = self.session_id         # 讓 result_grep 16 優先解析成目前 session 的 #16
        env["HARNESS_RAW_ARGS"] = getattr(self, "_raw_args", "") or ""   # action.args 原文（給要自己解析內容的技能）
        ws = getattr(self, "current_ros2_workspace", None) or {}
        env["ROS2_WORKSPACE"] = ws.get("path", "")                 # ROS 2 數據技能在容器內載入這個 Workspace（自訂訊息型別）
        env["ROS2_WORKSPACE_CONTAINER"] = ws.get("container", "")
        env.update(self.analysis_env())                  # 目前分析的數據、數據根目錄（ROS 2 數據技能省略數據路徑時用）
        if extra_env:
            env.update(extra_env)
        try:
            res = subprocess.run(
                [sys.executable, script_path] + clean_args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                cwd=self.current_cwd,
                env=env,
                timeout=TOOL_EXEC_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (
                f"[ERROR] 工具 {script_name} 執行逾時（超過 {TOOL_EXEC_TIMEOUT} 秒），已被系統強制終止。"
                f"這是 harness 的最後防線，各腳本自身應有更短的逾時；若經常觸發請檢查該腳本。"
            )
        except OSError as e:
            return f"[ERROR] 無法執行腳本 {script_name}（{type(e).__name__}: {e}）。下一步：把這段訊息告訴使用者（多半是權限或檔案系統的問題）。"
        if res.returncode == 0:
            return res.stdout.strip()
        # 腳本異常結束：優先用 stderr，沒有就用 stdout；兩者皆空也要給 AI 一個
        # 明確的失敗訊息，否則空字串會被誤判成「沒有工具需要執行」。
        # 統一補上 [ERROR] 前綴，讓 _content_for_context 能正確判定為失敗。
        output_text = res.stderr.strip() or res.stdout.strip() or "（沒有任何輸出）"
        if not output_text.startswith("[ERROR]"):
            output_text = f"[ERROR] 腳本 {script_name} 異常結束（exit code {res.returncode}）:\n{output_text}"
        return output_text
