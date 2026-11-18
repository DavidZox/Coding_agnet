"""TrajectoryMixin：操作軌跡（logs/trajectory.jsonl）——run_tool 每執行一支腳本記一筆並觸發原文存檔；/trajectory 列軌跡。"""
import json
import os
import re
import time
from .config import TRAJECTORY_LOG, TRAJECTORY_OUTPUT_HEAD


class TrajectoryMixin:


    def _script_skill_map(self):
        """scripts/<x>.py -> 技能名稱。依序：「<技能>.md 提到 scripts/<技能>_cmd.py」→ 規格裡 `EXECUTE: scripts/<x>.py` 的
        指令位置（腳本名稱跟技能不同的：list_dir＝ls_cmd.py、view_file＝cat_cmd.py…）→ 其餘只是提到的。每次重建（十幾個小檔案，
        成本可忽略），技能新增後不需重啟。只提到、不在指令位置的不算數：code_ast_reader 的範例把 scripts/ls_cmd.py 當成參數，
        以前 ls_cmd.py 被認成 code_ast_reader（字母排在前面），任務的 worker 用 list_dir 被擋成「這一步不能用 code_ast_reader」、
        軌跡記錯技能（2026-10-24 發現）。"""
        mapping, commands, mentions = {}, {}, {}
        if not os.path.isdir(self.tools_dir):
            return mapping
        for fname in sorted(os.listdir(self.tools_dir)):
            if not fname.endswith(".md"):
                continue
            skill = fname[:-3]
            try:
                with open(os.path.join(self.tools_dir, fname), "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            scripts = set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", text))
            if f"{skill}_cmd.py" in scripts:
                mapping[f"{skill}_cmd.py"] = skill
            for s in re.findall(r"EXECUTE:\s*scripts/([A-Za-z0-9_]+\.py)", text):
                commands.setdefault(s, skill)
            for s in scripts:
                mentions.setdefault(s, skill)
        for s, skill in list(commands.items()) + list(mentions.items()):
            mapping.setdefault(s, skill)
        return mapping

    def _next_id(self):
        """配一個新的全域編號（軌跡、工具結果存檔、被壓縮的對話片段存檔共用同一個序列，跨 session 不重複）。
        背景壓縮執行緒也會配編號（對話片段存檔），所以要上鎖；CLI 與 Web 同時開著時兩個 process 都在配，所以每次也看一下存檔目錄裡
        最大的編號（另一個 process 剛存的），不會配到同一個編號。"""
        with self._id_lock:
            self.trajectory_seq = max(self.trajectory_seq, self._max_archived_id()) + 1
            return self.trajectory_seq

    def _record_trajectory(self, script_name, args, output_text, cwd, container_cwd, target_container=""):
        """run_tool 每執行一支腳本（成功、失敗、逾時都算；找不到腳本的猜測不算）記一筆。
"""
        status = "ERROR" if output_text.lstrip().startswith("[ERROR]") else "PASS"
        record = {
            "id": self._next_id(),
            "kind": "exec",
            "ts": time.strftime("%m-%d %H:%M:%S"),
            "script": script_name,
            "skill": self._script_skill_map().get(script_name),
            "args": list(args),
            "command": self._format_execute(script_name, args),
            "cwd": cwd,
            "container_cwd": container_cwd,
            "target_container": target_container,
            "status": status,
            "output_head": output_text[:TRAJECTORY_OUTPUT_HEAD],
            "task": self.current_task or "",
        }
        receipt = getattr(self, "last_receipt", None)      # 腳本寫的收據（dispatch._exec_script）：軌跡記摘要，全文跟存檔放在一起
        if receipt:
            record["receipt"] = {k: receipt.get(k) for k in ("status", "error_kind", "counts", "truncated")}
        record["result_file"] = self._archive_tool_result(record, output_text, receipt)
        self.last_result_id = record["id"] if record["result_file"] else None
        self.last_result_file = record["result_file"]
        self.trajectory.append(record)
        self._append_trajectory_log(record)
        return record

    def add_trajectory_boundary(self, reason):
        """在軌跡記一個起點（/clear）；連續的起點只留一個。"""
        if not self.trajectory:
            return None  # 什麼都還沒執行（例如啟動時的 reset_conversation），不需要起點
        if self.trajectory[-1]["kind"] == "boundary":
            return None  # 連續的起點只留一個
        record = {"id": self._next_id(), "kind": "boundary", "ts": time.strftime("%m-%d %H:%M:%S"),
                  "reason": reason}
        self.trajectory.append(record)
        self._append_trajectory_log(record)
        return record

    def _append_trajectory_log(self, record):
        """追加到 logs/trajectory.jsonl（跨 session 的稽核記錄；寫不進去不影響主流程）。"""
        try:
            log_dir = os.path.join(self.script_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, TRAJECTORY_LOG), "a", encoding="utf-8") as f:
                f.write(json.dumps({"session": self.session_id, **record}, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError):
            pass

    @staticmethod
    def _quote_arg(arg):
        """顯示用：含空白／引號的參數以雙引號包住（與 AGENT.md 範例一致，shlex 可還原）。"""
        if arg == "" or any(c.isspace() for c in arg) or '"' in arg or "'" in arg:
            return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return arg

    def _format_execute(self, script_name, args):
        tail = " ".join(self._quote_arg(a) for a in args)
        return f"EXECUTE: scripts/{script_name}" + (f" {tail}" if tail else "")

    def format_trajectory(self):
        """/trajectory：列出本次 session 的軌跡（編號、成功／失敗、指令、所屬技能、起點）。"""
        if not self.trajectory:
            return "本次 session 尚未記錄任何腳本執行。"
        labels = {"clear": "/clear"}
        lines = ["🧭 操作軌跡（✅ 成功 / ❌ 失敗；#編號＝工具結果存檔的編號）："]
        for r in self.trajectory:
            if r["kind"] == "boundary":
                label = labels.get(r["reason"], r["reason"])
                lines.append(f"── 起點 #{r['id']}：{label}（{r['ts']}）──")
            else:
                mark = "✅" if r["status"] == "PASS" else "❌"
                skill = f"（{r['skill']}）" if r.get("skill") else ""
                lines.append(f"#{r['id']} {mark} {r['command']}{skill}")
        return "\n".join(lines)
