"""GuardMixin：執行前關卡——會改變實體／外部狀態的技能，執行前一律由程式要求使用者確認（CLI 問 y/n、Web 顯示按鈕）。

跟 Plan 模式的核准關卡同一個原則：確認由程式路徑保證，不靠模型記得要先問。判斷在這裡（guard_check），
執行在 DispatchMixin.run_tool：沒有 approved=True 就不執行被擋的技能（CLI／Web 以外的呼叫端也一樣擋得住）。
哪些技能要擋見 config.GUARDED_SKILLS；各技能的查詢用法放行（docker_runcmd／host_runcmd 的唯讀指令、workpackage_send --dry-run、
docker_ctl status、ROS2_param get、rmf_handshake status…），參數一律照腳本自己的解析（_guard_parse）判斷，不另外解析。工作流（workflow_run）在開始時確認：
workflow_guard_reason 列出到第一個【確認】之前會改變狀態的步驟，核准一次；【確認】之後接著做時再問一次。"""
import os
import re
import shlex
from .config import GUARD_DENIED_TAG, GUARDED_SKILLS
from .protocol import action_text


_GUARD_REASONS = {
    "workpackage_send": "送出工作包：實體 AMR 會開始移動",
    "workpackage_cancel": "取消工作包：正在執行的任務會停止派下一站",
    "overpending_cancel": "刪除卡在逾時區的任務",
    "docker_est": "建立新的容器",
    "docker_runcmd": "在容器內執行指令：這個指令不在唯讀清單裡，可能會改變容器內的狀態",
    "host_runcmd": "在主機上執行指令：這個指令不在唯讀清單裡，可能會改變主機或容器的狀態",
    "docker_ctl": "啟動／停止／重新啟動容器",
    "file_ops": "修改本機的檔案或目錄（原檔會先備份）",
    "ROS2_param": "修改執行中 node 的參數",
    "ROS2_topic_pub": "對 ROS 2 topic 發布訊息：正在跑的系統會收到",
    "ROS2_domain_id": "改 ROS_DOMAIN_ID：寫進容器的 ~/.bashrc，之後開的 shell（含其他 ROS 2 技能）都會用新的 domain",
    "ROS2_workspace_env": "在容器內載入 Workspace 後執行指令：這個指令不在唯讀清單裡，可能會改變容器內的狀態",
    "rmf_handshake": "手動回交握或補發完成訊號：調度系統會照這個訊號派工或前進到下一站",
}

# ---------------------------------------------------------------- docker_runcmd 的唯讀判斷
# 保守的白名單：每一段（&&、||、;、| 分隔）的指令都在清單裡、沒有寫檔的轉向或指令替換，才算唯讀。
# 判斷不了的一律當作「可能改變狀態」→ 請使用者確認（多問一次的代價，遠小於誤動到實體設備）。
_READONLY_CMDS = {
    "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "pwd", "echo", "printf", "printenv",
    "ps", "pgrep", "df", "du", "free", "uptime", "which", "whereis", "type", "whoami", "id", "uname",
    "stat", "file", "wc", "cut", "tr", "basename", "dirname", "realpath", "readlink",
    "nproc", "lscpu", "lsusb", "lspci", "lsblk", "column", "jq",
    "diff", "md5sum", "sha256sum", "test", "[", "true", "sleep", "cd", "export",
}
# 看起來唯讀、但某些參數會寫檔或改狀態的指令：帶了這些參數就不算唯讀
_WRITE_FLAGS = {
    "sort": {"-o", "--output"},      # sort -o 檔案 會寫檔
    "tree": {"-o"},                  # tree -o 檔案 會寫檔
    "date": {"-s", "--set"},         # date -s 會改系統時間
}
# 沒有參數時才唯讀：hostname 名稱 會改主機名稱；env 指令… 會執行後面的指令
_NO_ARGS_ONLY = {"hostname", "env"}
# source／. 只放行 ROS／colcon 的環境設定檔（setup.bash 這類）；source 任意腳本等於執行它
_SETUP_FILE = re.compile(r"^(local_)?setup\.(bash|sh|zsh)$")
# ros2 <群組> <動作>：只有查詢類的動作算唯讀（pub、call、set、send_goal、run、launch 都不是）；None＝整個群組都唯讀
_ROS2_READONLY = {
    "topic": {"list", "echo", "info", "hz", "bw", "type", "find", "delay"},
    "node": {"list", "info"},
    "service": {"list", "type", "find"},
    "param": {"list", "get", "describe"},   # dump 在舊版 ROS2 會寫檔，不放行
    "interface": {"list", "show", "package", "packages", "proto"},
    "action": {"list", "info"},
    "pkg": {"list", "prefix", "executables", "xml"},
    "lifecycle": {"get", "list", "nodes"},
    "doctor": None,
    "wtf": None,
}
_DOCKER_READONLY = {"ps", "logs", "inspect", "images", "image", "version", "info", "port", "top", "stats", "history", "diff"}
_GIT_READONLY = {"status", "log", "diff", "show", "branch", "rev-parse", "ls-files", "blame", "describe", "remote", "tag"}
_FIND_WRITES = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
_HARMLESS_REDIRECT = re.compile(r"\d?>\s*/dev/null|\d?>&\d")
# 一段一段檢查：&&、||、;、|、|&、換行，以及單一個 &（背景執行：`sleep 1 & rm -rf build` 的後半段也要檢查，以前整串被當成 sleep 放行）
_SEGMENT_SPLIT = re.compile(r"&&|\|\||\|&|;|\||\n|&")


def _segment_readonly(segment):
    try:
        toks = shlex.split(segment)
    except ValueError:
        return False
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):   # VAR=value 前綴只影響這一段的環境
        toks = toks[1:]
    if not toks:
        return True
    cmd = os.path.basename(toks[0])
    if cmd == "timeout":   # timeout [-s 訊號] [-k 秒] 秒數 指令…：檢查後面真正執行的指令
        i = 1
        while i < len(toks) and toks[i].startswith("-"):
            i += 2 if toks[i] in ("-s", "-k", "--signal", "--kill-after") else 1
        rest = toks[i + 1:]
        return bool(rest) and _segment_readonly(" ".join(shlex.quote(t) for t in rest))
    if cmd == "ros2":
        group = toks[1] if len(toks) > 1 else ""
        if group not in _ROS2_READONLY:
            return False
        verbs = _ROS2_READONLY[group]
        return verbs is None or (len(toks) > 2 and toks[2] in verbs)
    if cmd == "docker":         # host_runcmd 的 docker 查詢（ps、logs、inspect、images…）不改變狀態
        sub = [t for t in toks[1:] if not t.startswith("-")]
        if not sub:
            return False
        if sub[0] in ("network", "volume", "image", "container") and len(sub) > 1:
            return sub[1] in ("ls", "list", "inspect", "history")
        return sub[0] in _DOCKER_READONLY and not (sub[0] == "stats" and "--no-stream" not in toks)
    if cmd == "find":
        return not any(t in _FIND_WRITES for t in toks)
    if cmd == "git":            # 查詢類（status、log、diff…）；branch／tag／remote 帶參數會改狀態，只放行列出的寫法
        sub = [t for t in toks[1:] if not t.startswith("-")]
        if not sub or sub[0] not in _GIT_READONLY:
            return False
        return not (sub[0] in ("branch", "tag", "remote") and len(sub) > 1 and sub[1] not in ("-v", "--list", "show", "get-url"))
    if cmd == "top":
        return "-b" in toks
    if cmd in ("source", "."):
        return len(toks) == 2 and bool(_SETUP_FILE.match(os.path.basename(toks[1])))
    if cmd in _NO_ARGS_ONLY:
        return len(toks) == 1
    if cmd == "uniq":   # uniq 輸入 輸出 會寫進第二個檔
        return len([t for t in toks[1:] if not t.startswith("-")]) <= 1
    if cmd in _WRITE_FLAGS:
        return not any(t in _WRITE_FLAGS[cmd] or any(t.startswith(f + "=") for f in _WRITE_FLAGS[cmd]) for t in toks[1:])
    return cmd in _READONLY_CMDS


def is_readonly_shell(command):
    """容器內的 shell 指令是否只讀不寫。有 >／>> 轉向（/dev/null 除外）、反引號、$( ) 就不算；
    其餘每一段（&&、||、;、|、&、換行分開）的第一個字要在白名單裡（ros2 看群組與動作，find 不能帶 -delete／-exec／-fprint）。"""
    text = str(command or "").strip()
    if not text:
        return False
    text = _HARMLESS_REDIRECT.sub(" ", text)
    if re.search(r"[>`]|\$\(|<\(", text):
        return False
    segments = [s.strip() for s in _SEGMENT_SPLIT.split(text) if s.strip()]
    return bool(segments) and all(_segment_readonly(s) for s in segments)


class GuardMixin:

    def _guard_exempt(self, skill, args):
        """被擋的技能在這些參數下其實不會改變狀態：workpackage_send --dry-run、docker_runcmd／host_runcmd 的唯讀指令、各技能的查詢用法。
        參數一律照腳本自己的解析（parse_args）判斷——以前關卡自己再解析一次，跟腳本不一致時會被繞過（`WP1 a3 --desc --dry-run` 真的送出）。"""
        if skill == "workpackage_send":                # 真的 --dry-run 才不送（照腳本的解析：`--desc --dry-run` 這種被當成值的不算）
            from skills_system.scripts.workpackage_send_cmd import parse_args as send_args
            p = send_args(args)
            return not p.get("error") and bool(p.get("dry_run"))
        if skill == "docker_runcmd":                   # 指令照腳本的解析取（以前關卡自己解析：沒加引號的 `mkdir test` 被當成「容器 mkdir、指令 test」放行）
            p = self._guard_parse(skill, args)
            if p.get("error"):                         # 參數錯、不會自己結束的指令：腳本不執行，不必問
                return p.get("error_kind") in ("usage", "refused")
            command = p.get("command") or ""
            return "{" not in command and is_readonly_shell(command)   # 含 {…}（例如沒代入的佔位符）看不出實際指令，不放行
        if skill == "host_runcmd":                     # 主機上的唯讀指令（ls、cat、docker ps／logs、git status…）不用問；指令照腳本的解析取
            from skills_system.scripts.host_runcmd_cmd import parse_args as host_args
            _, command, err = host_args(args)
            return not err and "{" not in command and is_readonly_shell(command)
        if skill == "docker_ctl":                      # status／logs／inspect／env 是唯讀的
            p = self._guard_parse(skill, args)
            return bool(p.get("readonly")) or (bool(p.get("error")) and p.get("error_kind") == "usage")
        if skill == "ROS2_param":                      # list／get 是唯讀的（容器名稱可以在最前面）
            p = self._guard_parse(skill, args)
            return bool(p.get("readonly")) or bool(p.get("error"))
        if skill == "ROS2_topic_pub":                  # 參數錯的不會發布
            return bool(self._guard_parse(skill, args).get("error"))
        if skill == "ROS2_domain_id":                  # 查詢不用問；set 才會改 ~/.bashrc
            p = self._guard_parse(skill, args)
            return bool(p.get("error")) or p.get("action") != "set"
        if skill == "ROS2_workspace_env":              # 只確認、--discover、或唯讀的 --command 不用問
            p = self._guard_parse(skill, args)
            command = p.get("command") or ""
            return bool(p.get("error")) or not command or ("{" not in command and is_readonly_shell(command))
        if skill == "docker_est":                      # 參數錯的不會建容器
            return bool(self._guard_parse(skill, args).get("error"))
        if skill == "rmf_handshake":                   # status 是唯讀的（照腳本的解析：選項的值不會被當成動作）
            from skills_system.scripts.rmf_handshake_cmd import parse_args as hs_args
            p = hs_args(args)
            return not p.get("error") and bool(p.get("readonly"))
        return False

    def _guard_parse(self, skill, args):
        """照腳本自己的參數解析（各腳本的 parse_args／parse_cli，純函式、不執行任何動作）→ dict（至少有 error）。目標容器用 harness
        的狀態（腳本是從環境變數讀）；docker_runcmd／docker_ctl 要判斷第一個參數是不是容器時會查一次容器清單。"""
        target = getattr(self, "target_container", "") or ""
        try:
            if skill == "docker_runcmd":
                from skills_system.scripts.docker_runcmd_cmd import parse_args
                return parse_args(args, target=target)
            if skill == "docker_ctl":
                from skills_system.scripts.docker_ctl_cmd import parse_args
                return parse_args(args, target=target)
            if skill == "ROS2_param":
                from skills_system.scripts.ROS2_param_cmd import parse_cli
                return parse_cli(args, resolve=False)
            if skill == "ROS2_topic_pub":
                from skills_system.scripts.ROS2_topic_pub_cmd import parse_cli
                return parse_cli(args, resolve=False)
            if skill == "ROS2_domain_id":
                from skills_system.scripts.ROS2_domain_id_cmd import parse_cli
                return parse_cli(args)
            if skill == "ROS2_workspace_env":
                from skills_system.scripts.ROS2_workspace_env_cmd import parse_args
                return parse_args(args)
            if skill == "docker_est":
                from skills_system.scripts.docker_est_cmd import parse
                opts, err = parse(args)
                return dict(opts or {}, error=err)
        except Exception as e:   # noqa: BLE001  解析不了就當成要確認（寧可多問一次）
            return {"error": None, "parse_failed": f"{type(e).__name__}: {e}"}
        return {"error": None}

    def guard_check(self, parsed):
        """這一輪的 action 執行前需不需要使用者確認。回傳 None（不需要），或
        {"skill", "script", "command", "reason"} 給 CLI／Web 顯示。parsed 是 parse_agent_reply 的結果（或含 action 的 dict）。
        技能名稱（只載入規格）、找不到的腳本、偽技能（result_recall）都不需要確認。"""
        if not getattr(self, "guard_enabled", True) or not GUARDED_SKILLS:
            return None
        # 計畫執行前檢查（/plan_exec_guard）會擋下的動作不必再問使用者：run_tool 會直接回 [PLAN_BLOCKED]、不執行
        if self.plan_block_reason(parsed):
            return None
        return self.state_change_info(parsed)

    def state_change_info(self, parsed):
        """這個 action 會不會改變實體／外部狀態（不看 /guard 開關）：回傳 None 或 {skill, script, command, reason}。
        guard_check（執行前問使用者）與 PlanMixin 的計畫執行前檢查共用。"""
        if not GUARDED_SKILLS:
            return None
        action = (parsed or {}).get("action") if isinstance(parsed, dict) else None
        if not action:
            return None
        payload = action_text(action)
        parts = payload.split(maxsplit=1)
        raw_token = os.path.basename(parts[0])
        remainder = parts[1] if len(parts) > 1 else ""
        doc_name = raw_token[:-3] if raw_token.endswith(".md") else raw_token
        if os.path.exists(os.path.join(self.tools_dir, f"{doc_name}.md")):
            return None
        script_name = self._normalize_script_name(raw_token)
        script_path = os.path.join(self.base_path, "scripts", script_name)
        if not os.path.exists(script_path):
            return None
        skill_map = self._script_skill_map()
        skill = skill_map.get(script_name)
        args = self._parse_script_args(script_name, remainder)
        if skill not in GUARDED_SKILLS or self._guard_exempt(skill, args):
            return None
        if skill == "ops_run":
            # 確認的說明就是整份計畫（核准＝計畫裡標明的狀態變更都核准了）；沒有草稿時不用確認，ops_run 自己回錯誤
            reason = self.ops_guard_reason(remainder)
            if reason is None:
                return None
        elif skill == "workflow_run":
            # 開始：列出到第一個【確認】之前會改變狀態的步驟（核准＝那幾步都核准了）；--continue：那個【確認】的內容＋接下來的步驟；
            # 只查詢的工作流、取消、列出、參數錯（交給 workflow_run 回錯誤）不用確認
            reason = self.workflow_guard_reason(remainder)
            if reason is None:
                return None
        else:
            reason = _GUARD_REASONS.get(skill, "這個技能會改變系統狀態")
            if skill in ("docker_runcmd", "docker_ctl"):   # 實際會操作的容器（省略名稱、部分名稱時使用者看得到是哪一個）
                container = self._guard_parse(skill, args).get("container")
                if container:
                    reason += f"；容器：{container}"
        return {"skill": skill or script_name, "script": script_name,
                "command": f"scripts/{script_name} {remainder}".strip(), "reason": reason}

    @staticmethod
    def guard_prompt_text(info):
        """給使用者看的確認說明（CLI 印出、Web 顯示在確認列上方）。"""
        if "\n" in info["reason"]:   # ops_run／workflow_run：說明是整份計畫或工作流
            return f"🛡️ AI 要執行會改變系統狀態的動作，需要你確認：\n- 技能：{info['skill']}\n{info['reason']}"
        return (f"🛡️ AI 要執行會改變系統狀態的動作，需要你確認：\n"
                f"- 技能：{info['skill']}（{info['reason']}）\n"
                f"- 指令：{info['command']}")

    @staticmethod
    def guard_denied_text(info):
        """使用者拒絕時交給模型的結果（包成 [tool result] 進主對話）。"""
        return (f"{GUARD_DENIED_TAG} 使用者沒有同意執行 {info['skill']}（{info['command']}）：這個動作沒有執行，系統狀態沒有改變。"
                f"不要再送出同一個指令；等使用者說明要怎麼調整，或改做別的。")

    @staticmethod
    def guard_blocked_text(info):
        """run_tool 沒拿到 approved=True 就碰到被擋的技能時的回傳（CLI／Web 以外的呼叫端、或漏接確認的程式路徑）。"""
        return (f"{GUARD_DENIED_TAG} {info['skill']} 會改變系統狀態（{info['reason']}），需要使用者在畫面上確認才能執行；"
                f"這次沒有執行。")
