"""TurnGuardMixin：主對話一個回合裡的兩個程式把關（從 coding worker 移植過來的做法，CLI、Web、評測共用）。

1. 卡住偵測（run_tool 的外層呼叫 note_tool_result）：同一個回合裡，同樣的動作（command＋args）得到同樣的結果——
   第 REPEAT_HINT_AT 次在工具回傳後面附一句提醒（換做法，不要再重複）；第 REPEAT_STOP_AT 次設 self.stuck，回合迴圈看到就停下來
   交回使用者。同一個錯誤（同樣的動作、同樣的 [ERROR] 開頭）不管中間做了什麼，第 REPEAT_STOP_AT 次也算卡住。
   實測小模型在這種狀態下幾乎不會自己跳出來（coding worker 一直重送同一份內容、主對話一直重查同一個不存在的路徑），
   只靠步數上限（MAX_AUTO_ITERATIONS＝25）要白跑很多輪。
2. 沒有執行卻宣稱做完了（claim_without_action）：這一回合一個工具都沒有執行，回覆卻說「已重新啟動／已建立／已刪除…」，
   多半是模型以為說了就等於做了（跟 coding worker「沒有改任何檔案就回報完成」同一類）。提醒一次：要做就填 action，
   只是說明就不要說已經做了。用否定、疑問、條件句的回覆（還沒、如果、要不要…嗎）不算。
3. 依數據分析的報告回答時把事實寫成因果、或寫錯事實（analysis_reply_check）：這一回合執行了 analysis_run，回覆卻寫「L16 觸發…導致…」——
   報告只有事實與先後順序（「前後 1 秒內」只是時間上的對照），誰造成誰要對照源碼另外分析；或回答裡的變化、某一刻的值、「回到初始」
   跟那份報告的事實對不上（agent_core/claims.py，事實從 job 讀）。提醒一次改寫。報告的原文（Log）本來就有的字、否定或條件的說法
   （不代表誰造成誰、如果…）不算。實測：Web 的 /analyze，主對話的第一個回答寫了因果，也寫錯過變化的方向（「status.level 從 0 變為 2（E6）」）。
回合的起點是使用者送出新訊息（set_current_task 會呼叫 begin_turn）。
評測的對照組（evals/chat/run.py --suite robust 的穩健性情境）用環境變數 AGENT_ABLATE=turn_guard 把兩個把關都關掉；平常不要設。
"""
import json
import os
import re

from . import claims
from .config import ANALYSIS_ANSWER_NOTE, ANALYSIS_REPORT_HEAD
from .protocol import action_text

REPEAT_HINT_AT = 2
# v4.1：第 2 次提醒、第 3 次加強提醒（要它換技能或參數）、第 4 次才停——E6 穩健性實驗裡「第 3 次就停」切斷了模型自己
# 換做法的機會；不連續、但同樣的錯誤也提醒（以前沒提醒就直接停）。評測的對照組用 AGENT_TURN_GUARD_RULE=v4 換回舊規則。
REPEAT_STOP_AT = int(os.environ.get("AGENT_REPEAT_STOP_AT", "4"))
# 只認子句開頭（回覆開頭、標點之後）或「我／我們」後面的「已經…」：前面有主詞的「指令已停止發布」「系統已完成初始化」
# 是在描述數據或系統的狀態，不是 AI 說自己做了（實測：回答數據分析報告的追問被當成宣稱已停止，模型改口道歉、沒回答問題）
_CLAIM_RE = re.compile(
    r"(?:^|(?<=[，。；！!、：:「（(\n])|(?<=我)|(?<=我們))(已經?|剛剛?)(?:幫你|為你|替你|順利|成功)?(?:地)?"
    r"(執行|完成|重新啟動|重啟|啟動|停止|關閉|建立|新增|刪除|移除|修改|更新|切換|設定|安裝|寫入|儲存|送出|發布|部署|下載|上傳|複製|搬移|清除|派送|派工)")
_HEDGE_RE = re.compile(r"(沒有|尚未|還沒|未能|無法|不能|失敗|如果|若是|假如|要不要|是否|可以幫|需要我|請問|嗎[？?]|\?|？)")
# 說要去做、卻沒有動作（「我會先查…」「讓我找一下…」，action 是 null 就結束）：要有表示「接下來要做」的字，動詞後面不是了／過／到／完
# （「我查到…」「我先查了…」是做過的事）。2026-10-23 fs_find_value：第一步只回「我會先查…」，使用者看到的是沒有結果的承諾（待辦 16）
_PROMISE_RE = re.compile(
    r"(?:讓我|我(?:現在|馬上|立刻|接著|這就)?(?:會|將|來|去)|我先|接下來我?(?:會|將)?|我們(?:先|來|會))\s*(?:先|再|來|去)?\s*"
    r"(?:幫你|為你|替你)?\s*(查詢|查看|查一下|查|檢查|確認|讀取|讀|看一下|看看|搜尋|尋找|找出|找|列出|執行|分析|重新啟動|重啟|啟動|修改|改|派)"
    r"(?![了過到完])")
# 依數據分析的報告回答時不能有的說法：把先後寫成誰造成誰（報告只有事實與時間上的對照）
_CAUSAL_WORDS = ("導致", "造成", "引起", "引發", "觸發", "使得", "歸因", "根因")
# 回覆的一行寫到報告的哪裡：報告裡的編號（E#、L#、T#）、Topic 名稱、+秒（之後的回合只核對這種行，跟報告無關的回答不核對）
_REPORT_REF = re.compile(r"(?<![A-Za-z0-9_])[ELT]\d+(?![0-9])|(?<![A-Za-z0-9_/])/[A-Za-z0-9_][A-Za-z0-9_/]*|[+＋]\s?\d{1,4}\.\d+\s?(?:s|秒)")
# 同一個子句裡在它前面有這些字＝否定或條件的說法（「時間上的先後不代表誰造成誰」「如果是…造成的」「是否…導致」），不算
_CAUSAL_HEDGE = re.compile(r"(不代表|不表示|不等於|不能說|不能確定|無法判斷|無法確定|看不出|不是|並非|沒有|未|是否|有沒有|如果|若|假如|"
                           r"要對照|需要對照|另外分析|源碼)")


class TurnGuardMixin:
    def begin_turn(self):
        """使用者送出新訊息：清掉上一回合的重複計數、卡住旗標、執行次數。"""
        self._rep_key = None
        self._rep_count = 0
        self._rep_errors = {}
        self.stuck = None
        self.turn_tool_runs = 0
        self._claim_nudged = False
        self._analysis_report = None
        self._analysis_job_id = None
        self._analysis_nudged = False

    def note_tool_result(self, parsed, output):
        """run_tool 執行完一個動作之後呼叫：計數、必要時在 output 後面附提醒或設 self.stuck。回傳（可能附了提醒的）output。"""
        if not isinstance(output, str) or not parsed or not parsed.get("action"):
            return output
        if not hasattr(self, "_rep_errors"):
            self.begin_turn()
        self.turn_tool_runs += 1
        if output.startswith(ANALYSIS_REPORT_HEAD):   # 這一回合的回覆要依這份報告：analysis_reply_check 核對（最後那行回答的說明不算報告的字）
            self._analysis_report = "\n".join(ln for ln in output.splitlines() if not ln.startswith(ANALYSIS_ANSWER_NOTE))
            m = re.search(r"（job ([^\s：）]+)", output.splitlines()[0])
            self._analysis_job_id = m.group(1) if m else None
            # 之後的回合（追問、討論這份報告）也核對寫到報告的那幾行：最近一份報告一直算數，直到下一份報告或 /clear
            self._analysis_ctx = {"report": self._analysis_report, "job": self._analysis_job_id}
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
        """這一回合沒有執行任何工具、回覆卻宣稱已經做了某件事，或說要去做卻沒有動作：回傳要接在對話後面的提醒（每回合最多一次），
        否則 None。在問使用者（嗎？、請問、要不要…）或有條件（如果…）的不算。"""
        if not hasattr(self, "_rep_errors"):
            self.begin_turn()
        if self._claim_nudged or self.turn_tool_runs or not parsed or parsed.get("action") or not parsed.get("valid", True):
            return None
        if "turn_guard" in os.environ.get("AGENT_ABLATE", ""):
            return None
        reply = (parsed.get("reply") or "").strip()
        if _HEDGE_RE.search(reply):
            return None
        m = _CLAIM_RE.search(reply)
        if not m:
            p = _PROMISE_RE.search(reply)
            if not p:
                return None
            self._claim_nudged = True
            self._add_notice(f"⚠️ AI 說要「{p.group(0)}」卻沒有執行任何工具：已提醒它直接做（或把要問的問清楚）。")
            return ("[harness] 你說要「" + p.group(0) + "」，但這一回合沒有執行任何工具（action 是 null），使用者看到的是還沒有結果的承諾。"
                    "要做就現在在 action 填要執行的技能（不用先問使用者）；需要使用者先回答的，直接在 reply 問清楚。")
        self._claim_nudged = True
        self._add_notice(f"⚠️ AI 的回覆說「{m.group(0)}」，但這一回合沒有執行任何工具：已提醒它確認（要做就實際執行，沒做就照實說）。")
        return ("[harness] 你在這一回合沒有執行任何工具（action 都是 null），但回覆說「" + m.group(0) + "」。系統沒有執行過任何動作，"
                "使用者要求的事其實還沒有發生。如果要做，現在就在 action 填要執行的技能；如果只是說明或建議，請改口，不要說已經做了。")

    def analysis_reply_check(self, parsed):
        """依數據分析的報告回答：回覆把報告的事實寫成因果（導致、造成、觸發…），或寫的變化、值跟報告的事實對不上 → 回傳要接在對話
        後面的提醒（每回合最多一次），否則 None。執行 analysis_run 的那一回合核對整個回覆；之後的回合（追問、討論那份報告）只核對寫到
        報告的那幾行（_about_report：報告裡的編號、Topic、+秒），跟報告無關的回答不核對。最近一份報告一直算數，直到下一份報告或 /clear
        （實測：追問「為什麼一直鎖著」的回答寫了「觸發了緊急停止鎖定機制」「LiDAR 斷線導致…」，以前只核對執行報告的那一回合，沒有提醒）。
        報告裡本來就有的字（Log 原文）、同一個子句前面有否定或條件的說法不算。"""
        ctx = getattr(self, "_analysis_ctx", None)
        if not ctx or getattr(self, "_analysis_nudged", False) or not parsed or parsed.get("action") or not parsed.get("valid", True):
            return None
        if "turn_guard" in os.environ.get("AGENT_ABLATE", ""):
            return None
        report = ctx["report"]
        reply = parsed.get("reply") or ""
        if not getattr(self, "_analysis_report", None):   # 不是這一回合的報告：只看寫到報告的那幾行
            reply = _about_report(reply, report)
            if not reply:
                return None
        hits = []
        for w in _CAUSAL_WORDS:
            if w in report:
                continue
            for m in re.finditer(w, reply):
                start = max(reply.rfind(p, 0, m.start()) for p in "，。；;,、\n！？!?") + 1
                if not _CAUSAL_HEDGE.search(reply[start:m.start()]):
                    hits.append(w)
                    break
        facts = self._analysis_report_facts(ctx.get("job"))
        wrong = claims.reply_problems(reply, facts) if facts else []
        if not hits and not wrong:
            return None
        self._analysis_nudged = True
        parts = []
        if hits:
            self._add_notice(f"⚠️ AI 依數據分析的報告回答時寫了「{'、'.join(hits)}」（把先後寫成因果），報告只有事實：已請它改寫。")
            parts.append("你的回答寫了「" + "、".join(hits) + "」，把報告裡的事件寫成誰造成誰。數據分析的報告只有事實與先後順序"
                         "（「前後 1 秒內」「同時」只是時間上的對照），沒有判斷原因。請改寫：照報告說明發生了什麼、時間與先後順序，可以引用編號"
                         "（E#、L#）；不要用「導致、造成、引起、觸發」把先後寫成因果。使用者想知道原因時，說明原因要對照源碼另外分析。")
        if wrong:
            self._add_notice("⚠️ AI 的回答有 " + str(len(wrong)) + " 處跟報告的事實對不上（" + "；".join(wrong)[:200] + "）：已請它改正。")
            parts.append("你的回答有幾句跟報告的事實對不上（程式跟量到的事實逐句核對）：\n" + "\n".join(f"- {w}" for w in wrong)
                         + "\n請照報告改正這幾句（每則重點下面列了引用的事件的完整內容：從什麼變成什麼、到最後的值），其他照舊。")
        return "[harness] " + "\n\n".join(parts)

    def _analysis_report_facts(self, jid=None):
        """數據分析報告的事實（logs/analysis_jobs/<job>/job.json 的 facts）；讀不到就是 None（只核對因果的用詞）。"""
        jid = jid or getattr(self, "_analysis_job_id", None)
        jobs_dir = getattr(self, "analysis_jobs_dir", None)
        if not jid or not jobs_dir:
            return None
        try:
            with open(os.path.join(jobs_dir(), os.path.basename(jid), "job.json"), encoding="utf-8") as f:
                return json.load(f).get("facts")
        except (OSError, ValueError):
            return None


def _about_report(reply, report):
    """回覆裡寫到這份報告的那幾行：有報告裡出現過的編號（E#、L#、T#）、Topic 名稱或 +秒。"""
    known = set(m.group().replace("＋", "+").replace(" ", "") for m in _REPORT_REF.finditer(report))
    keep = [ln for ln in reply.splitlines()
            if any(m.group().replace("＋", "+").replace(" ", "") in known for m in _REPORT_REF.finditer(ln))]
    return "\n".join(keep)
