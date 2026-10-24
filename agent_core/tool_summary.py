"""ToolSummaryMixin：工具回傳的任務導向提煉——summarize_tool_result（大量回傳自動提煉）與 _result_recall（回存檔依問題重新提煉），
兩者共用 agent_core/extract.py 的 Extraction（程式切段 → 每段一個 worker → 整合，程式核對引用的行號，全部的中間產物存檔）。
這裡負責：錨點（使用者的目標、這一步的目的、recall 的問題與背景）、交給主對話的文字（_render_tool_summary）與下一步建議。"""
import re
import shlex
from skills_system.scripts import _results_common
from .config import (
    CONVERSATION_ARCHIVE_SCRIPT,
    DERIVED_RESULT_SCRIPTS,
    RECALL_MAX_RECORDS,
    TOOL_RESULT_TOKEN_THRESHOLD,
    TOOL_SUMMARY_TAG,
    VISION_ARCHIVE_SCRIPT,
)
from .extract import Extraction, lines_text
from .protocol import action_text, parse_agent_reply


class ToolSummaryMixin:

    def _last_assistant_step(self):
        """最近一則 assistant 回覆解析成 {thought, reply, action}：這一步「為什麼執行、執行了什麼」。
        CLI／Web 都在 run_tool 之前就把該則回覆加進 self.messages，所以提煉時最後一則 assistant 就是下這個工具的那一輪。
        給獨立 session 當第二層聚焦依據（第一層是使用者的目標，見 _build_task_anchor_text）；沒有就回 None。"""
        for m in reversed(self.messages):
            if m['role'] != 'assistant':
                continue
            parsed = parse_agent_reply(m['content'])
            if parsed["valid"]:
                return {"thought": parsed["thought"], "reply": parsed["reply"], "action": parsed["action"]}
            return {"thought": "", "reply": parsed["reply"], "action": None}
        return None

    @staticmethod
    def _gap_reported(not_covered):
        """not_covered 是否代表「真的有缺口」（而不是模型寫「無」「沒有」這類空值的各種說法）。"""
        text = str(not_covered or "").strip()
        return bool(text) and text.rstrip("。.") not in ("無", "沒有", "none", "None", "N/A", "n/a")

    @staticmethod
    def _render_tool_summary(out, ids):
        """Extraction 的結果 → 交給主對話的固定結構純文字：回答／相關事實（附原文的行號）／錯誤／未涵蓋／還需要的舊存檔／之後可能想知道的。
        行號是存檔原文的行號（result_view <編號> --from <行> 看得到同一行）；好幾份存檔時寫成「#12 行 40」。"""
        data = out["data"]
        multi = len(ids) > 1

        def ref(it):
            where = lines_text(it.get("nums") or [])
            rid = ids[it["src"]] if multi and it.get("src") is not None and it["src"] < len(ids) else ""
            return f"（{'#' + str(rid) + ' ' if rid else ''}行 {where}）" if where else (f"（#{rid}）" if rid else "")

        answer = str(data.get("answer") or "").strip()
        if out.get("fallback"):
            answer = "（整合沒有成功；以下是各段 worker 摘出、程式核對過的事實）"
        lines = [f"回答：{answer or '（沒有給出回答）'}"]
        if out.get("answer_missing"):
            lines.append(f"（程式核對：回答裡的「{'」「'.join(out['answer_missing'])}」在原文找不到，以下面附行號的事實為準）")
        where = "、".join(f"#{i}" for i in ids)
        lines.append(f"相關事實（行號＝存檔 {where} 原文的行號）：" if ids else "相關事實：")
        lines += [f"- {it['text']}{ref(it)}" for it in data.get("facts") or []] or ["- （原始輸出中沒有與任務直接相關的事實）"]
        errors = data.get("errors") or []
        if errors:
            lines.append("錯誤／異常：")
            lines += [f"- {it['text']}{ref(it)}" for it in errors]
        not_covered = " ".join(str(data.get("not_covered") or "").split())
        if ToolSummaryMixin._gap_reported(not_covered):
            lines.append(f"未涵蓋：{not_covered}")
        related = [r for r in (data.get("related_records") or []) if isinstance(r, dict) and r.get("id")]
        if related:
            lines.append("這個問題可能還需要之前的存檔：")
            lines += [f"- #{r['id']}：{str(r.get('reason') or '').strip() or '（未給理由）'}" for r in related]
        questions = [q for q in (data.get("suggested_questions") or []) if isinstance(q, dict) and str(q.get("question") or "").strip()][:3]
        if questions:
            # 給決策 AI 自己參考的方向，不是要它照抄給使用者看：不用「可追問」這種標籤式字眼，並要求改寫成自然的一句話
            lines.append(f"使用者接下來可能還想知道（存檔 {where} 原文裡有、上面沒寫）（你自己判斷要不要主動問；要問就用一句自然的話問，"
                         f"不要條列、不要照抄下面的文字）：")
            lines += [f"- {str(q['question']).strip()}" for q in questions]
        return "\n".join(lines)

    @staticmethod
    def _validate_related(data, allowed_ids):
        """related_records 只留檢索清單裡真的有的編號（小模型可能編出不存在的編號、或把這一份自己列進去），最多 2 筆；
        就地改寫 data["related_records"] 成 [{"id": int, "reason": str}]。"""
        out, seen = [], set()
        for r in data.get("related_records") or []:
            if not isinstance(r, dict):
                continue
            m = re.search(r"\d+", str(r.get("id") or ""))
            rid = int(m.group()) if m else None
            if rid is None or rid not in allowed_ids or rid in seen:
                continue
            seen.add(rid)
            out.append({"id": rid, "reason": " ".join(str(r.get("reason") or "").split())[:80]})
            if len(out) >= 2:
                break
        data["related_records"] = out
        return out

    def _followup_guidance(self, ids, out, recalled=False, directive=True):
        """接在提煉結果後面、給 main session 的下一步建議——獨立 session 看過完整原文與檢索清單後的判斷，依序：還需要之前的存檔 → 把
        「這一份＋那幾份」一起 recall（同一個整合才比得了）；有沒讀到的段落或缺口 → 自然地問使用者或用更具體的問題 recall；已經回答 → 直接回答。
        提煉沒有成功（回覆不是 JSON）時照實說，不說成「已經回答」。directive=False（claude_code 模式）：只陳述事實，下一步由模型自己決定。"""
        ids = [str(i) for i in (ids if isinstance(ids, (list, tuple)) else [ids]) if i]
        if not ids:
            return "你看不到原始輸出：需要其他資訊時，換更精確的參數重新執行工具，不要憑空補上。"
        label = "、".join(f"#{i}" for i in ids)
        view = f"要看某一條事實的原文：result_view {ids[0]} --from <行號> --lines 30。"
        ok = out is not None and out.get("structured") and out.get("data") is not None
        if not ok:
            return (f"提煉沒有成功（獨立 session 的回覆不是預期的格式），上面是它的原文，可能不完整：需要細節時用 result_recall {ids[0]} "
                    f"\"<使用者的問題>\" 再提煉一次，或用 result_view／result_grep 自己看存檔 {label} 的原文；不要憑空補上。")
        data = out["data"]
        related = [str(r["id"]) for r in (data.get("related_records") or [])]
        new = [r for r in related if r not in ids]
        has_gap = self._gap_reported(data.get("not_covered"))
        if not directive:
            parts = [f"原文在存檔 {label}。"]
            if new:
                reasons = "；".join(f"#{r['id']}：{r.get('reason') or '（未給理由）'}" for r in data["related_records"] if str(r["id"]) in new)
                parts.append(f"獨立 session 認為這個問題可能還需要之前的存檔（{reasons}）。")
            if has_gap:
                parts.append("「未涵蓋」的部分原文裡沒有，或這次沒讀到。")
            parts.append("接下來怎麼做由你決定：看某一段用 result_view、找某個字串用 result_grep、換個問題再 result_recall，或直接回答。")
            return "".join(parts)
        if recalled:
            base = f"不要再對 {label} 重複同一個問題的 recall。{view}"
        else:
            base = (f"完整原始輸出已存成 #{ids[0]}：之後使用者追問這份輸出裡上面沒寫到的內容時，執行 result_recall {ids[0]} \"<使用者的話>\" "
                    f"回原文提煉（只有要找某個字串出現在哪幾行才用 result_grep），不要重新執行同一個工具。{view}")
        if out.get("fallback"):
            return base + "整合沒有成功，上面的事實是各段直接摘出的：據此回答，不要補上沒列的內容。"
        if new and len(ids) < RECALL_MAX_RECORDS:
            combo = ",".join((ids + new)[:RECALL_MAX_RECORDS])
            return base + (f"獨立 session 判斷這個問題還需要之前的存檔 {'、'.join('#' + r for r in new)} 一起看才答得完整："
                           f"下一輪直接執行 result_recall {combo} \"<使用者的話>\"（逗號隔開的幾份原文交給同一次提煉一起整合），"
                           f"拿到後再回答，不要先問使用者、也不要重跑當時的工具。")
        if out.get("notes"):
            return base + ("有些段落這次沒有讀到（見「未涵蓋」）：上面已經回答的就直接回答；使用者要的正好在沒讀到的那幾行時，用更具體的問題 "
                           f"result_recall {ids[0]} \"<問題>\"（會依問題重新挑段落），或 result_view 看那幾行。")
        if has_gap and data.get("suggested_questions"):
            return base + ("上面的缺口原文裡沒有：下一輪用 reply 自然地問使用者一句話（不要條列、不要照抄），不要自己選一個方向去執行，"
                           "除非使用者這句話已經對應到其中一個方向。")
        return base + "上面已經回答了使用者的問題：直接據此回答或做任務的下一步，不需要再 recall；後面列的方向只是額外可能有興趣的，順口提一句或略過都可以。"

    def _extract(self, kind, sources, purpose, question, exclude_ids):
        """跑一次 Extraction（附工具使用檢索清單，排除正在讀的存檔），驗證 related_records。回傳 Extraction.run() 的結果；
        模型呼叫丟例外時回 {"structured": False, "data": None, "raw": "[ERROR] …", "error": …}，呼叫端照實交給主對話。"""
        catalog, allowed = self._tool_use_catalog(exclude_ids)
        try:
            out = Extraction(self, kind, sources, purpose, catalog, allowed, question=question, allowed=purpose).run()
        except Exception as e:   # noqa: BLE001  Ollama 沒有回應、存檔寫不進去…：照實回報，不讓例外變成「解析指令失敗」
            return {"structured": False, "data": None, "raw": "", "error": f"{type(e).__name__}: {e}", "job": None}
        if out.get("structured") and out.get("data") is not None:
            self._validate_related(out["data"], allowed)
        return out

    def summarize_tool_result(self, result, tool_tokens, step=None, result_id=None):
        """任務導向提煉（Task-Oriented Extraction）：把超過門檻的工具回傳交給獨立、乾淨的 session（不接觸 self.messages）依問題提煉，
        主對話只收到重點。錨點有兩層：1. 使用者的目標（_build_task_anchor_text：Objective、使用者最近 3 句原話）；
        2. 這一步的目的（_last_assistant_step：決策 AI 剛才的 thought／reply 與執行的 action）。
        提煉讀全文（agent_core/extract.py：放得進一段就一次寫完；更長的依結構切段、每段一個 worker、再整合），每條事實附原文的行號、
        由程式核對；以前超過 16000 字只讀頭尾，中間的內容主對話永遠看不到。
        result_id 預設取最近一次 run_tool 的存檔編號：回答回填到 index.md，index_hint 記進 tools_use_index.md（result_* 這類看舊存檔的
        衍生輸出不記）——這份永久累加、跨 session 存活，讓再久以前的工具回傳也有機會被日後的 main session 從檢索清單裡認出來。
        結尾的下一步建議見 _followup_guidance。"""
        anchor = self._build_task_anchor_text()
        result_id = self.last_result_id if result_id is None else result_id
        step = step if step is not None else (self._last_assistant_step() or {})
        step_lines = []
        if step.get("action"):
            step_lines.append(f"執行的工具：{action_text(step['action'])}")
        if step.get("thought"):
            step_lines.append(f"決策 AI 執行前的想法：{step['thought']}")
        if step.get("reply"):
            step_lines.append(f"決策 AI 對使用者的說明：{step['reply']}")
        step_text = "\n".join(step_lines) or "（沒有取得這一步的說明，請以使用者的目標為依據）"
        purpose = f"【使用者的目標】\n{anchor}\n\n【這一步的目的（決策 AI 為什麼執行這個工具）】\n{step_text}"
        record = next((r for r in reversed(self.trajectory) if r.get("id") == result_id), None) if result_id else None
        script = (record or {}).get("script") or (action_text(step["action"]).split()[0] if step.get("action") else "工具")
        sources = [{"rid": str(result_id or "?"), "label": f"{script}" + (f"（#{result_id}）" if result_id else ""), "lines": result.splitlines()}]
        question = " ".join(x for x in (self.current_task or "", action_text(step.get("action")) if step.get("action") else "",
                                        step.get("thought") or "") if x)
        out = self._extract("tool_summary", sources, purpose, question, (result_id,))
        ok = out.get("structured") and out.get("data") is not None
        ids = [str(result_id)] if result_id else []
        if ok:
            body = self._render_tool_summary(out, ids)
            answer = str(out["data"].get("answer") or "").strip()
        else:
            body = (f"（獨立 session 提煉失敗：{out['error']}）" if out.get("error") else out.get("raw") or "（獨立 session 沒有回覆）")
            answer = ""
        self.last_tool_summary = {"structured": ok, "input_tokens": tool_tokens, "summary_tokens": self.count_tokens(body),
                                  "model": self.summary_model, "result_id": result_id, "job": out.get("job"), "mode": out.get("mode"),
                                  "chunks": out.get("chunks"), "read": out.get("read"), "dropped": out.get("dropped")}
        if result_id and answer:
            self.update_result_answer(result_id, answer)
        if ok and (record or {}).get("script") not in DERIVED_RESULT_SCRIPTS:
            self._append_tool_use_index(result_id, self.last_result_file, out["data"].get("index_hint"))
        status = "失敗（[ERROR]）" if result.lstrip().startswith("[ERROR]") else "成功"
        how = (f"分 {out['chunks']} 段由獨立 session 各讀一段再整合" if out.get("mode") == "merge" else "由獨立 session 讀完整原文")
        job = f"；提煉過程存在 logs/extract_jobs/{out['job']}/" if out.get("job") else ""
        note = (f"（原始輸出約 {tool_tokens} tokens，超過門檻 {TOOL_RESULT_TOKEN_THRESHOLD}；以上依使用者目標與這一步的目的{how}提煉"
                f"{job}，完整內容已顯示給使用者。{self._followup_guidance(ids, out)}）")
        return f"{TOOL_SUMMARY_TAG}\n執行結果：{status}\n{body}\n{note}"

    def _result_recall(self, remainder):
        """result_recall 偽技能——追問任何存檔內容的主要路徑（檢索清單裡的舊紀錄、或剛剛的提煉沒寫到的細節）：main session 帶編號＋使用者的
        問題原文執行；這裡把那幾份存檔的完整原文交給同一套提煉（Extraction：切段 → worker → 整合，附檢索清單讓它判斷還需要哪一筆），
        main session 只收到提煉後的重點（附行號）與下一步建議。跟 result_grep 的差別是語意由獨立 session 理解，不是 main session 自己想
        關鍵字比對字面。錨點用任務線（_build_task_anchor_text：最新一句＋前幾句）——實測使用者回答追問時最新一句常只剩「第一個」，
        模型給的參數只當聚焦點。可以一次給多個編號（1,2，最多 RECALL_MAX_RECORDS 份）：要一起看幾份存檔時（比較兩次的清單），每一份的段落
        交給 worker、同一個整合看全部（以前只能 recall 一份時會來回跳——讀 #1 的說「還需要 #2」，讀 #2 的又說「還需要 #1」）。
        這是 main session 主動選的一次動作，照樣記軌跡、產生新的存檔編號；但不記進 tools_use_index.md（清單留原本的那幾筆）。"""
        usage = '用法：result_recall <編號>[,<編號>] "<使用者的問題原文>"（編號＝檢索清單或提煉結果裡的 #數字，最多 3 個）'
        try:
            parts = shlex.split(remainder) if remainder.strip() else []
        except ValueError:
            parts = remainder.split()
        if not parts:
            return f"[ERROR] 需要指定存檔編號與問題。{usage}。"
        ref_arg, question = parts[0], " ".join(parts[1:]).strip()
        refs = [r.strip() for r in re.split(r"[,，、]+", ref_arg) if r.strip()]
        if not all(re.fullmatch(r"#?\d+|latest", r) for r in refs):
            return (f"[ERROR] 第一個參數要是存檔編號（例如 12 或 12,15），收到「{ref_arg}」。{usage}；問題放第二個參數、用雙引號包起來。")
        if not question:
            return f"[ERROR] 需要問題內容。{usage}。"
        loaded, missing, extra = [], [], refs[RECALL_MAX_RECORDS:]
        for ref in refs[:RECALL_MAX_RECORDS]:
            path, err = _results_common.resolve_result(ref, self.results_dir(), session=self.session_id)
            if err:
                missing.append((ref.lstrip("#"), err))
                continue
            meta, lines = _results_common.read_body(path)
            rid = str(meta.get("id") or ref.lstrip("#"))
            if rid not in {x[0] for x in loaded}:
                loaded.append((rid, meta, lines))
        if not loaded:
            reasons = "；".join(self._missing_reason(rid, err) for rid, err in missing)
            return f"[ERROR] {reasons}"
        ids = [rid for rid, _, _ in loaded]
        label = "、".join(f"#{i}" for i in ids)
        sources = []
        for rid, meta, lines in loaded:
            script = meta.get("script") or "?"
            hint = self._tool_use_index_hint(rid)
            if script == CONVERSATION_ARCHIVE_SCRIPT:
                # 對話片段不是工具輸出：告訴獨立 session 怎麼讀，讓它回答「當時談了什麼、決定了什麼、使用者怎麼說」
                kind, bg = "過去的對話片段", (f"這份是過去被壓縮的對話原文（{meta.get('command') or ''}），不是工具輸出——[user] 是使用者當時說的話、"
                                       f"[assistant] 是 AI 當時的想法與回覆、[harness …] 是當時的工具回傳；回答時說明當時談了什麼、查到什麼、"
                                       f"決定了什麼，使用者的原話與名稱、數值照抄")
            elif script == VISION_ARCHIVE_SCRIPT:
                # 附圖分析：原圖沒有保存，只有當時視覺模型提取的文字——文字裡沒有的不能補，要更多細節只能請使用者重新附圖
                kind, bg = "附圖分析", (f"這份是過去使用者附圖時系統的影像分析結果（{meta.get('command') or ''}），不是工具輸出；原圖沒有保存，"
                                     f"只能根據這份文字回答，文字裡沒有的寫進 not_covered（例如「當時的影像分析沒有提到…，需要的話請使用者重新附圖」），"
                                     f"不要推測影像內容；當時使用者的說明：{meta.get('task') or '(沒有)'}")
            else:
                kind, bg = script, f"當時的任務：{meta.get('task') or '(未知)'}；執行的指令：{meta.get('command') or script}"
            sources.append({"rid": rid, "label": f"{kind}（#{rid}，{meta.get('ts') or '?'}）", "lines": lines,
                            "background": bg + (f"；檢索清單對它的描述：{hint}" if hint else "")})
        hints = {self._tool_use_index_hint(i) for i in ids}
        # 錨點用 harness 自己記的任務線，不靠模型抄：實測小模型會把清單上的描述抄進參數當問題，而使用者回答追問時最新一句常只剩「第一個」。
        # 模型給的參數只當聚焦點，跟使用者原話或清單描述一樣時就是噪音、不帶。
        user_now = " ".join((self.current_task or "").split())
        focus = question if user_now and question != user_now and question not in hints else ""
        primary = user_now or question
        anchor = self._build_task_anchor_text() if user_now else question
        purpose = (f"【使用者現在的問題】\n{anchor}\n" + (f"【決策 AI 要聚焦的點】\n{focus}\n" if focus else "")
                   + f"\n【{'這份' if len(ids) == 1 else '這幾份'}存檔的背景（不是現在要回答的問題）】\n"
                   + "\n".join(f"#{s['rid']}：{s['background']}" for s in sources))
        out = self._extract("recall", sources, purpose, f"{primary} {focus}".strip(), ids)
        if out.get("structured") and out.get("data") is not None:
            body = self._render_tool_summary(out, ids)
        elif out.get("error"):
            body = f"（獨立 session 提煉失敗：{out['error']}）"
        else:
            body = out.get("raw") or "（獨立 session 沒有回覆）"
        notes = [self._missing_reason(rid, err) for rid, err in missing]
        if extra:
            notes.append(f"一次最多讀 {RECALL_MAX_RECORDS} 份，{'、'.join('#' + r.lstrip('#') for r in extra)} 這次沒有讀（要的話另外 recall）。")
        gone = "".join(f"（{n}）\n" for n in notes)
        harness = self.context_mode == "harness"
        how = f"，分 {out['chunks']} 段由獨立 session 各讀一段再整合" if out.get("mode") == "merge" else ""
        job = f"；提煉過程存在 logs/extract_jobs/{out['job']}/" if out.get("job") else ""
        output_text = (f"{TOOL_SUMMARY_TAG}\n重新讀取存檔 {label} 的完整原文{how}，針對「{primary}」"
                       f"{'（聚焦：' + focus + '）' if focus else ''}提煉：\n{gone}{body}\n"
                       f"（以上是獨立 session 回到完整原文、針對使用者的問題提煉的重點{job}。"
                       f"{self._followup_guidance(ids, out, recalled=True, directive=harness)}）")
        self._record_trajectory(
            "result_recall_cmd.py", [ref_arg, question], output_text,
            self.current_cwd, self.container_cwd, self.target_container,
        )
        return output_text

    def _missing_reason(self, rid, err):
        """存檔找不到的原因：編號比目前最大的編號還大（沒有這個編號）、檢索清單有它但檔案不在（超過保留上限被清掉）、其他（resolve_result 的訊息）。"""
        rid = str(rid).lstrip("#")
        if rid.isdigit() and int(rid) > self._max_archived_id() and int(rid) > getattr(self, "trajectory_seq", 0):
            return f"#{rid} 不存在（目前最大的存檔編號是 #{self._max_archived_id()}）：編號抄錯了，看檢索清單或用 result_list 確認"
        if rid.isdigit() and self._tool_use_index_hint(rid):
            return (f"#{rid} 的原始檔已經超過保留上限被清掉：直接告訴使用者這筆資料已經不在，需要的話重新執行當時的工具，"
                    f"不要換個編號亂試")
        return f"#{rid}：{str(err).replace('[ERROR] ', '')}"
