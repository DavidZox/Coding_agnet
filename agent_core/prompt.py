"""PromptMixin：組 system prompt 與每次送出時附在最尾端的動態區，以及 Plan 模式的請求文字。

排列依「多久變一次」決定（Ollama 只重用跟上一次請求相同的開頭，從第一個不同的 token 開始全部重算）：
- system prompt（get_system_prompt）只放不常變的：AGENT.md、目前上下文模式的規則、長期記憶、滾動摘要、
  使用者原話、技能索引、工具使用檢索清單。清單一千多 tokens、只在跑完獨立 session 時多一筆，留在這裡最划算。
- 動態區（build_state_tail）放小而常變的：Current Agent State、Objective、檢索清單最新一筆。
  每次呼叫只接在送出快照的最後一則訊息後面（ask_ai），不寫進 self.messages——切目錄不再讓整段歷史重算，
  而且它們離生成點最近，小模型最看得到。"""
import os
import re
from . import prompt_files
from .config import CONTEXT_MODES, MEMORY_MAX_CHARS, WORKFLOWS_ENABLED

# 摘要裡「看起來是技能」的名稱：反引號包住的 snake_case（可帶 scripts/ 前綴與 _cmd.py／.py 後綴），或 scripts/<x>_cmd.py
_SKILL_REF_RE = re.compile(r"`(?:scripts/)?([a-z][a-z0-9]*(?:_[a-z0-9]+)+?)(?:_cmd)?(?:\.py)?`|scripts/([a-z][a-z0-9_]*?)_cmd\.py")



def _sp(key, /, **fields):
    """prompts/harness/system_prompt.md 的一則：主對話 system prompt 裡程式組進去的部分。"""
    return prompt_files.load("harness/system_prompt.md", key, **fields)


def _st(key, /, **fields):
    """prompts/harness/state_tail.md 的一則：動態區（每次送出時接在最後）。"""
    return prompt_files.load("harness/state_tail.md", key, **fields)


def _an(key, /, **fields):
    """prompts/harness/anchor.md 的一則：交給獨立 session 的「使用者的目標」。"""
    return prompt_files.load("harness/anchor.md", key, **fields)


class PromptMixin:

    # ---------------------------------------------------------------- 長期記憶
    def _memory_entries(self):
        """Memory.md 的條目（非空、不是 # 標題或 > 說明的行）；檔案不在時回 None。"""
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return None
        return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith(("#", ">"))]

    def load_long_term_memory(self, max_chars=None):
        """整份載入 Memory.md（以條目為單位，不再只讀最後 30 行——條目一多，最舊、往往最基礎的規則會無聲消失）。
        超過 MEMORY_MAX_CHARS 才丟最舊的條目，並在 system prompt 註明還有幾條沒載入、UI 提醒使用者整理。
        開頭一句說明寫入時間的意義：描述某個時間點狀態的條目只代表當時，回答現況前要重查。"""
        budget = MEMORY_MAX_CHARS if max_chars is None else max_chars
        entries = self._memory_entries()
        if not entries:
            self.memory_dropped = 0
            return _sp("memory_none")
        kept, used = [], 0
        for e in reversed(entries):
            if kept and used + len(e) > budget:
                break
            kept.append(e)
            used += len(e)
        kept.reverse()
        dropped = len(entries) - len(kept)
        if dropped and dropped != self.memory_dropped:
            # 不在這裡呼叫 _add_notice：這個方法可能在 messages_lock 裡被呼叫（壓縮完刷新 system prompt），
            # _add_notice 要拿另一把鎖，順序跟背景壓縮相反。改成留一個字串，pop_notices 取走時一起送出。
            self._memory_warning = (f"⚠️ 長期記憶有 {dropped} 條較舊的條目超過載入上限（{budget} 字，AGENT_MEMORY_MAX_CHARS）沒有載入，"
                                    f"AI 看不到它們；請整理 Memory.md（合併或刪除過時的條目）。")
        self.memory_dropped = dropped
        guide = (_sp("memory_guide"))
        note = "\n" + _sp("memory_dropped", count=dropped) if dropped else ""
        return guide + "\n" + "\n".join(kept) + note

    # ---------------------------------------------------------------- 新的使用者訊息
    def end_plan_for_new_task(self):
        """使用者送出新訊息時（CLI／Web／評測共用）：任務引擎還沒接著問的確認（使用者先前捨棄了那份報告）不再自動接著問——
        停下來等確認的任務本身留著，使用者同意時主對話用 task_run --continue。回傳要顯示給使用者的說明（沒有要說的回 None）。"""
        if getattr(self, "task_pending_approval", None):
            self.task_pending_approval = None
            return "📝 停下來等確認的任務還留著：要繼續就跟 AI 說（task_run --continue），不要了就說取消。"
        return None

    # ---------------------------------------------------------------- 各區塊
    def _build_objective_prompt(self):
        """若有設定 sticky objective，組成提醒 AI 優先遵守的區塊；否則回傳空字串。"""
        if not self.sticky_objective:
            return ""
        return (_st("objective", objective=self.sticky_objective))

    def _build_task_anchor_text(self):
        """獨立 session（summarize_tool_result、_result_recall）的「使用者的目標」，依序組合：
        - sticky_objective：使用者用 /objective set 設定的最高優先目標（有設定才有）
        - current_task：使用者最新的一句話（每次送出新訊息都由 set_current_task 更新，/clear 清空）
        - task_history：任務線，連同最新一句共最近 TASK_HISTORY_KEEP（3）句使用者的原話；最新一句常只是
          「第一個」這種短回答，原本要做什麼要看前幾句
        有幾層就給幾層，不互斥。「這一步的目的」（決策 AI 的 thought／reply／action）由 _last_assistant_step
        另外提供，這裡不夾帶 AI 的回覆。"""
        parts = []
        if self.sticky_objective:
            parts.append(_an("objective", objective=self.sticky_objective))
        if self.current_task:
            parts.append(_an("latest", task=self.current_task))
            earlier = [t for t in self.task_history[:-1] if t and t != self.current_task]
            if earlier:
                # 任務線：使用者回答追問時最新一句常只剩關鍵字（例如「看 motor_rear_left」），原本要做什麼在前幾句
                parts.append(_an("earlier") + "\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(earlier, 1)))
        return "\n".join(parts) if parts else _an("none")

    def _user_words_block(self):
        """被壓縮掉的對話裡使用者的原話（程式逐字保留，見 CompressionMixin._keep_user_words）。對話片段存檔的編號與描述
        另外列在「過去的對話片段」一節（ToolUseIndexMixin._conversation_index_block）。"""
        if not self.user_words:
            return ""
        lines = [_sp("user_words_header")]
        lines += [f"- [{w['ts']}] {w['text']}" if w.get("ts") else f"- {w['text']}" for w in self.user_words]
        if self.user_words_dropped:
            lines.append(_sp("user_words_more", count=self.user_words_dropped))
        return "\n".join(lines)

    # ---------------------------------------------------------------- 滾動摘要（可能是之前的 session 留下的）
    def stale_skill_names(self, text):
        """文字裡提到、但目前不存在的技能名稱（沒有 tools/<名稱>.md，也沒有 scripts/<名稱>_cmd.py）。
        滾動摘要跨啟動接回，裡面可能還寫著已經移除的技能（實測：plan_task 移除後，舊摘要的未完成事項寫著「指導系統
        執行 plan_task 技能」，新 session 的模型照著去叫，拿到的是一個不存在的技能）。只看同一行有「技能」或是
        scripts/ 路徑的名稱，上下文模式名稱（claude_code）不算，避免把一般的識別字當成技能。"""
        names = set()
        for line in str(text or "").splitlines():
            for m in _SKILL_REF_RE.finditer(line):
                name = m.group(1) or m.group(2)
                if not name or name in CONTEXT_MODES or (m.group(1) and "技能" not in line):
                    continue
                if os.path.exists(os.path.join(self.tools_dir, f"{name}.md")) or \
                        os.path.exists(os.path.join(self.base_path, "scripts", f"{name}_cmd.py")):
                    continue
                names.add(name)
        return sorted(names)

    def clean_summary(self, text):
        """把摘要裡提到「目前不存在的技能」的行拿掉（標題行留著）。不在 system prompt 點名說「X 不能用」：實測（e4b，
        舊摘要寫著 plan_task）點名之後 3 次有 3 次反而先去叫 plan_task——小模型看到名稱就被提醒，否定句沒什麼用；
        整行拿掉之後名稱不再出現。原本的摘要檔不改，下一次壓縮時交給摘要模型的也是清過的版本，新摘要自然就沒有了。"""
        stale = self.stale_skill_names(text)
        if not stale:
            return text
        pat = re.compile("|".join(re.escape(n) for n in stale))
        return "\n".join(ln for ln in str(text).splitlines() if ln.lstrip().startswith("#") or not pat.search(ln))

    def _summary_block(self):
        """system prompt 的滾動摘要一節（提到已不存在技能的行已拿掉，見 clean_summary）。摘要是之前的 session 留下的
        （啟動時接回、這次還沒壓縮過）就註明：裡面的進度與未完成事項可能已經過時，使用者沒提起就不要主動接續。"""
        if not self.rolling_summary:
            return _sp("summary_none")
        body = self.clean_summary(self.rolling_summary)
        if getattr(self, "summary_carried_from", None):
            body = _sp("summary_carried", source=self.summary_carried_from) + "\n" + body
        return body

    # ---------------------------------------------------------------- system prompt（不常變的部分）
    def get_system_prompt(self):
        profile = ""
        if os.path.exists(self.profile_file):
            with open(self.profile_file, "r", encoding="utf-8") as f:
                profile = f.read().strip()
        with open(self.index_file, "r", encoding="utf-8") as f:
            skills = f.read().strip()
        if not WORKFLOWS_ENABLED:   # 評測「沒有工作流」的對照：工作流那一節整段拿掉
            skills = re.sub(r"^## 工作流.*?(?=^## )", "", skills, flags=re.S | re.M)
        mode_rules = self.context_mode_rules()
        blocks = [
            profile,
            _sp("context_mode_rules", mode=self.context_mode, rules=mode_rules) if mode_rules else _sp("context_mode", mode=self.context_mode),
            _sp("memory", memory=self.load_long_term_memory()),
            _sp("summary", summary=self._summary_block()),
            self._user_words_block(),
            self._conversation_index_block(),
            _sp("skills", skills=skills),
            self._tool_use_index_block().strip(),
        ]
        return "\n\n".join(b for b in blocks if b)

    # ---------------------------------------------------------------- 動態區（每次送出時附在最尾端）
    
    def build_state_tail(self):
        """每次呼叫主模型時附加目前狀態，不寫進 self.messages。"""

        state = (
            _st("agent_state", cwd=self.current_cwd, container_cwd=self.container_cwd, target=self.target_container or _st("target_none"))
        )

        # 只有 Workspace 所屬容器與目前目標容器相同時，
        # 才將它當成目前可直接沿用的 Workspace。
        workspace_state = getattr(
            self,
            "current_ros2_workspace",
            {"container": "", "path": ""},
        ) or {}

        workspace_container = workspace_state.get("container", "")
        workspace_path = workspace_state.get("path", "")

        if (
            workspace_container
            and workspace_path
            and workspace_container == self.target_container
        ):
            workspace_line = (
                _st("workspace_ok", path=workspace_path, container=workspace_container)
            )
        elif workspace_path:
            workspace_line = (
                _st("workspace_other", target=self.target_container or _st("workspace_no_target"), container=workspace_container)
            )
        else:
            workspace_line = (
                _st("workspace_none")
            )

        blocks = [
            state,
            workspace_line,
            self.analysis_state_line(),   # 📊 目前分析的數據、最近一次 analysis_run（analysis_job.py）
            self._build_objective_prompt(),
            self.tool_use_index_pointer(),
        ]

        body = "\n\n".join(b for b in blocks if b)

        return _st("header") + "\n" + body

