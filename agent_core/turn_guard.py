"""TurnGuardMixin：主對話一個回合裡的兩個程式把關（從 coding worker 移植過來的做法，CLI、Web、評測共用）。

1. 卡住偵測（run_tool 的外層呼叫 note_tool_result）：同一個回合裡，同樣的動作（command＋args）得到同樣的結果——
   第 REPEAT_HINT_AT 次在工具回傳後面附一句提醒（換做法，不要再重複）；第 REPEAT_STOP_AT 次設 self.stuck，回合迴圈看到就停下來
   交回使用者。同一個錯誤（同樣的動作、同樣的 [ERROR] 開頭）不管中間做了什麼，第 REPEAT_STOP_AT 次也算卡住。
   實測小模型在這種狀態下幾乎不會自己跳出來（coding worker 一直重送同一份內容、主對話一直重查同一個不存在的路徑），
   只靠步數上限（MAX_AUTO_ITERATIONS＝25）要白跑很多輪。
2. 沒有執行卻宣稱做完了（claim_without_action）：這一回合一個工具都沒有執行，回覆卻說「已重新啟動／已建立／已刪除…」，
   多半是模型以為說了就等於做了（跟 coding worker「沒有改任何檔案就回報完成」同一類）。提醒一次：要做就填 action，
   只是說明就不要說已經做了。用否定、疑問、條件句的回覆（還沒、如果、要不要…嗎）不算。
回合的起點是使用者送出新訊息（set_current_task 會呼叫 begin_turn）。
評測的對照組（benchmark_study 的穩健性情境）用環境變數 AGENT_ABLATE=turn_guard 把兩個把關都關掉；平常不要設。
"""
import os
import re

from .protocol import action_text

REPEAT_HINT_AT = 2
# v4.1：第 2 次提醒、第 3 次加強提醒（要它換技能或參數）、第 4 次才停——E6 穩健性實驗裡「第 3 次就停」切斷了模型自己
# 換做法的機會；不連續、但同樣的錯誤也提醒（以前沒提醒就直接停）。評測的對照組用 AGENT_TURN_GUARD_RULE=v4 換回舊規則。
REPEAT_STOP_AT = int(os.environ.get("AGENT_REPEAT_STOP_AT", "4"))
# 只認子句開頭（回覆開頭、標點之後）或「我／我們」後面的「已經…」：前面有主詞的「指令已停止發布」「系統已完成初始化」
# 是在描述數據或系統的狀態，不是 AI 說自己做了（實測：回答數據診斷報告的追問被當成宣稱已停止，模型改口道歉、沒回答問題）
_CLAIM_RE = re.compile(
    r"(?:^|(?<=[，。；！!、：:「（(\n])|(?<=我)|(?<=我們))(已經?|剛剛?)(?:幫你|為你|替你|順利|成功)?(?:地)?"
    r"(執行|完成|重新啟動|重啟|啟動|停止|關閉|建立|新增|刪除|移除|修改|更新|切換|設定|安裝|寫入|儲存|送出|發布|部署|下載|上傳|複製|搬移|清除|派送|派工)")
_HEDGE_RE = re.compile(r"(沒有|尚未|還沒|未能|無法|不能|失敗|如果|若是|假如|要不要|是否|可以幫|需要我|請問|嗎[？?]|\?|？)")


class TurnGuardMixin:
    def begin_turn(self):
        """使用者送出新訊息：清掉上一回合的重複計數、卡住旗標、執行次數。"""
        self._rep_key = None
        self._rep_count = 0
        self._rep_errors = {}
        self.stuck = None
        self.turn_tool_runs = 0
        self._claim_nudged = False

    def note_tool_result(self, parsed, output):
        """run_tool 執行完一個動作之後呼叫：計數、必要時在 output 後面附提醒或設 self.stuck。回傳（可能附了提醒的）output。"""
        if not isinstance(output, str) or not parsed or not parsed.get("action"):
            return output
        if not hasattr(self, "_rep_errors"):
            self.begin_turn()
        self.turn_tool_runs += 1
        if "turn_guard" in os.environ.get("AGENT_ABLATE", ""):
            return output
        key = (action_text(parsed["action"]).strip(), output.strip()[:500])
        if key == self._rep_key:
            self._rep_count += 1
        else:
            self._rep_key, self._rep_count = key, 1
        errors = 0
        if output.lstrip().startswith("[ERROR]"):
            self._rep_errors[key] = errors = self._rep_errors.get(key, 0) + 1
        v4 = os.environ.get("AGENT_TURN_GUARD_RULE") == "v4"
        stop_at = 3 if v4 else REPEAT_STOP_AT
        if self._rep_count >= stop_at or errors >= stop_at:
            times = max(self._rep_count, errors)
            self.stuck = f"「{key[0][:80]}」已經 {times} 次得到同樣的結果"
            self._add_notice(f"⛔ AI 用同樣的動作 {times} 次都得到同樣的結果（{key[0][:60]}），這一回合先停在這裡，避免一直重試；"
                             "可以補充說明、指出正確的路徑或參數，或換個方式要求。")
            return output + ("\n（系統：同樣的動作已經 {0} 次得到同樣的結果，這一回合停在這裡；使用者看得到上面的結果。"
                             "等使用者的下一句話，不要再執行同一個動作。）").format(times)
        times = max(self._rep_count, errors)
        if not v4 and times >= REPEAT_HINT_AT + 1:
            return output + (f"\n（系統提醒：同樣的動作已經 {times} 次得到同樣的結果，這個做法行不通。現在就換：用另一個技能"
                             "（例如在主機上操作 docker 用 host_runcmd、找檔案用 find_file）、換參數或路徑，"
                             "或直接回覆使用者目前的狀況與你的建議。" + ("再重複一次，這一回合就會停下來。）" if times >= stop_at - 1 else "）"))
        if self._rep_count >= REPEAT_HINT_AT or (not v4 and errors >= REPEAT_HINT_AT):
            warn = "再重複一次，這一回合就會停下來。" if times >= stop_at - 1 else ""
            return output + ("\n（系統提醒：你已經用同樣的動作得到同樣的結果了，不要再重複——換一個做法（例如先確認路徑、名稱或參數），"
                             f"或直接回覆使用者目前的狀況。{warn}）")
        return output

    def claim_without_action(self, parsed):
        """這一回合沒有執行任何工具、回覆卻宣稱已經做了某件事：回傳要接在對話後面的提醒（每回合最多一次），否則 None。"""
        if not hasattr(self, "_rep_errors"):
            self.begin_turn()
        if self._claim_nudged or self.turn_tool_runs or not parsed or parsed.get("action") or not parsed.get("valid", True):
            return None
        if "turn_guard" in os.environ.get("AGENT_ABLATE", ""):
            return None
        reply = (parsed.get("reply") or "").strip()
        m = _CLAIM_RE.search(reply)
        if not m or _HEDGE_RE.search(reply):
            return None
        self._claim_nudged = True
        self._add_notice(f"⚠️ AI 的回覆說「{m.group(0)}」，但這一回合沒有執行任何工具：已提醒它確認（要做就實際執行，沒做就照實說）。")
        return ("[harness] 你在這一回合沒有執行任何工具（action 都是 null），但回覆說「" + m.group(0) + "」。系統沒有執行過任何動作，"
                "使用者要求的事其實還沒有發生。如果要做，現在就在 action 填要執行的技能；如果只是說明或建議，請改口，不要說已經做了。")
