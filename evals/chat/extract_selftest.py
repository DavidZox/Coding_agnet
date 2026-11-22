"""工具回傳的提煉（agent_core/extract.py）與存檔（result_*）的離線自我測試：假的 ollama.chat 依 schema 回答，不需要 Ollama。

    python3 evals/chat/extract_selftest.py

測的是 harness 的程式（不是模型能力；模型能力用 evals/chat/run.py 量）：
- 切段：依結構切（章節、--- #序號、表格的列），每段附前情（狀態列、章節標題、表頭），大綱；
- 核對：事實寫的數字與名稱要在引用的行（前後 2 行＋縮排的上層）裡——寫錯對象、編出來的名稱擋下，一般的詞、使用者問題裡的數字放行；
  名稱要整個對上（av2_test 不算 nav2_test 裡有；待辦 4j ①）；
- 一次寫完（短的輸出）與分段（worker → 整合）：每條事實附行號、對不上的拿掉、回答找不到的字請整合修一次、還是不行就標明；
  整合失敗由程式排出各段的事實；每一次的切段、模型呼叫、結果都存在 logs/extract_jobs/<編號>/；
- result_recall：好幾份一起讀、編號錯／檔案被清掉的說明、提煉失敗照實回報；
- 行號：result_view、result_grep、提煉結果、claude_code 模式的截斷說明都是原文的行號；result_view --outline；
  檔案的行號（待辦 4k ②）：照收據把存檔的每一行對到檔案（只認收據裡的絕對路徑，result_grep 的存檔編號不算），事實附「檔案:行號」，
  回答把存檔的行號寫成檔案的行號交回修一次、還是錯就標明；
- 子工作階段的說法（待辦 4k ①）：提煉結尾的下一步建議、沒有提煉時的說明、claude_code 的截斷說明只寫 result_grep、result_view；
- 存檔：刪最舊的照編號（#1000 不會排在 #999 前面）、清單不列原始檔已經被清掉的；
- dispatch：只認輸出最後的狀態標記；工作目錄不能用時換回專案目錄並回 [ERROR]。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts", "web_app", "vision"]

ROBOTS = [(f"tb{i}", round(20 + i * 3.5, 1), "IDLE" if i % 3 else "CHARGING") for i in range(1, 41)]


def fleet_yaml():
    """40 台車的 YAML（名字在上面一行、電量在下面幾行：核對要看縮排的上層）。"""
    lines = ["[PASS] 觀察 '/fleet_states' 一筆：40 台車", "## 機器人（40 台）"]
    for name, bat, mode in ROBOTS:
        lines += [f"- name: {name}", f"  mode: {mode}", "  location:", "    x: 1.0", "    y: 2.0", f"  battery_percent: {bat}"]
    return "\n".join(lines)


class FakeExtract:
    """假的提煉模型：worker 依原文找「battery_percent」的行回事實（名字從往上找）；整合把 worker 的事實照抄、回答寫第一條。
    mode 可以讓它故意出錯：bad_worker（事實寫錯車號）、bad_answer（回答寫原文沒有的數字）、synth_fail（整合回非 JSON）、raise（丟例外）。"""

    def __init__(self, mode=""):
        self.mode, self.calls = mode, []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = set((format or {}).get("properties", {})) if isinstance(format, dict) else set()
        user = messages[-1]["content"] if messages else ""
        self.calls.append(("worker" if "relevant" in props else "synth" if "index_hint" in props else "other", user))
        if self.mode == "raise":
            raise ConnectionError("ollama 沒有回應")
        if "relevant" in props:
            facts, name = [], None
            for m in re.finditer(r"^\s*(\d+)→(.*)$", user, re.M):
                n, text = int(m.group(1)), m.group(2)
                nm = re.search(r"name: (tb\d+)", text)
                if nm:
                    name = nm.group(1)
                b = re.search(r"battery_percent: ([\d.]+)", text)
                if b and name and float(b.group(1)) < 40:
                    shown = name if self.mode != "bad_worker" else "tb99"
                    facts.append({"text": f"{shown} 電量 {b.group(1)}%", "lines": str(n)})
            data = {"relevant": bool(facts), "facts": facts, "errors": [], "summary": f"{len(facts)} 台電量低於 40%"}
        elif "index_hint" in props:
            if self.mode == "synth_fail" and "【各段提煉的事實" in user:
                return {"message": {"content": "（不是 JSON）"}, "prompt_eval_count": 10, "eval_count": 5}
            facts = [{"text": m.group(1), "lines": m.group(2), "record": ""}
                     for m in re.finditer(r"^- (tb\d+ 電量 [\d.]+%)（行 ([\d、\-]+)）", user, re.M)]
            if not facts:   # 一次寫完：自己從原文找
                for m in re.finditer(r"^\s*(\d+)→\s*battery_percent: ([\d.]+)", user, re.M):
                    if float(m.group(2)) < 40:
                        facts.append({"text": f"電量 {m.group(2)}%", "lines": m.group(1), "record": ""})
            answer = "電量最低的是 tb1（23.5%）" if self.mode != "bad_answer" else "電量最低的是 tb1（12.3%）"
            data = {"answer": answer, "facts": facts, "errors": [], "not_covered": "無", "suggested_questions": [],
                    "index_hint": "想找低電量的車：40 台車的狀態，含 tb1、tb2", "related_records": []}
        else:
            return {"message": {"content": "（摘要）"}, "prompt_eval_count": 10, "eval_count": 5}
        return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 100, "eval_count": 20}


def make_env():
    tmp = tempfile.mkdtemp(prefix="extract_selftest_")
    for item in COPY:
        src = os.path.join(PROJECT, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
    # 這裡測主迴圈本身（直接執行 ls、cat 這些工具）：拿掉領域的清單，工具不交給領域（分領域在 evals/orch/selftest.py 測）
    os.remove(os.path.join(tmp, "skills_system", "DOMAIN.md"))
    return tmp


def main():
    tmp = make_env()
    os.environ["AGENT_PERF_LOG"] = "0"
    os.environ["AGENT_EXTRACT_CHUNK_CHARS"] = "1500"   # 小一點才切得出好幾段（正式的是 8000 字）
    sys.path.insert(0, tmp)
    cwd = os.getcwd()
    os.chdir(tmp)
    results = []
    try:
        import ollama
        ollama.list = lambda: {"models": []}
        from agent_core.agent import SkillAgent
        from agent_core import extract
        from skills_system.scripts import _results_common as rc
        agent = SkillAgent(model="gemma4:e4b")
        agent.current_cwd = tmp

        def archive(text, script="ROS2_topic_echo_cmd.py", task="哪幾台車電量低於 40%"):
            agent.set_current_task(task)
            rec = agent._record_trajectory(script, ["/fleet_states"], text, tmp, "", "")
            return rec["id"]

        def check(name, fn):
            try:
                fn()
                results.append((name, True, ""))
                print(f"✅ {name}")
            except Exception as e:   # noqa: BLE001
                results.append((name, False, traceback.format_exc()))
                print(f"❌ {name}：{e}")

        def t_chunker():
            lines = fleet_yaml().splitlines()
            spans = rc.chunk_lines(lines, 1000)
            assert len(spans) > 3 and spans[0][0] == 0 and spans[-1][1] == len(lines), spans
            assert all(sum(len(x) + 1 for x in lines[a:b]) <= 1000 for a, b in spans), "每段不超過篇幅"
            assert all(lines[a].startswith("- name:") for a, _ in spans[1:]), "切在一台車的開頭，不切在縮排的中間"
            ctx = rc.chunk_context(lines, spans[1][0])
            assert ctx == [0, 1], f"前情＝狀態列＋章節標題：{ctx}"
            table = ["[PASS] 共 50 列", "## 表", "| 名稱 | 值 |", "|---|---|"] + [f"| r{i} | {i} |" for i in range(50)]
            spans = rc.chunk_lines(table, 200)
            ctx = rc.chunk_context(table, spans[1][0])
            assert 2 in ctx and 3 in ctx, f"表格從中間開始時要帶表頭：{ctx}"
            assert rc.outline(lines) == [(2, "## 機器人（40 台）", len(lines) - 1)], rc.outline(lines)

        def t_grounding():
            lines = fleet_yaml().splitlines()
            src = "\n".join(lines)
            i6 = next(i for i, x in enumerate(lines) if x == "- name: tb6") + 1
            ev = "\n".join(lines[x - 1] for x in extract.evidence_lines(lines, [i6 + 5]))
            assert "tb6" in ev, "縮排的上層（名字）要算進引用的原文"
            assert extract.missing_tokens("tb6 電量 41.0%", ev, src) == [], "名字在上層、數值在引用的行：對得上"
            assert extract.missing_tokens("tb7 電量 41.0%", ev, src) == ["tb7"], "寫錯對象：tb7 在原文別的地方"
            assert extract.missing_tokens("tb99 電量 41.0%", ev, src) == ["tb99"], "編出來的車號（原文有 tbN 這種寫法）"
            assert extract.missing_tokens("tb6 的 ROS2 電量 41.0%", ev, src) == [], "一般的詞（ROS2）不核對"
            assert extract.missing_tokens("tb6 電量 41.5%", ev, src) == ["41.5"], "數值要照抄"
            assert extract.missing_tokens("低於 40% 的有 3 台", ev, src, allowed="哪幾台電量低於 40%") == [], "問題裡的數字、10 以下的整數不核對"
            assert extract.parse_lines("行 40-42、50", 100) == [40, 41, 42, 50] and extract.lines_text([40, 41, 42, 50]) == "40-42、50"
            ex = extract.Extraction(agent, "tool_summary", [{"rid": "1", "label": "fleet", "lines": lines}], "哪幾台", question="", allowed="")
            g, bad = ex._ground({"text": "tb7 電量 41.0%", "lines": str(i6 + 5), "record": ""})
            assert g is None and "tb7" in bad, "寫了行號卻對不上（tb6 的值寫成 tb7）：不在別的地方幫它找"
            g, bad = ex._ground({"text": "tb6 電量 41.0%", "lines": str(i6), "record": ""})
            assert g is not None, f"引用一筆紀錄的開頭：底下的欄位也算 {bad}"
            g, bad = ex._ground({"text": "tb6 電量 41.0%", "lines": "", "record": ""})
            assert g is not None and g["nums"], "沒寫行號：找出現那些字的行補上"

        def t_direct():
            text = "\n".join(fleet_yaml().splitlines()[:30])
            rid = archive(text)
            ollama.chat = fake = FakeExtract()
            out = agent.summarize_tool_result(text, 600, step={"action": {"command": "scripts/ROS2_topic_echo_cmd.py", "args": "/fleet_states"}},
                                              result_id=rid)
            assert len(fake.calls) == 1 and fake.calls[0][0] == "synth", [c[0] for c in fake.calls]
            assert out.startswith("[tool result - 任務導向摘要]") and "（行 " in out and "電量 23.5%" in out, out
            assert f"行號＝存檔 #{rid} 原文的行號" in out and f"result_view {rid} --from" in out, out
            job = agent.last_tool_summary["job"]
            d = os.path.join(tmp, "logs", "extract_jobs", job)
            assert os.path.exists(os.path.join(d, "job.json")) and os.path.exists(os.path.join(d, "calls.jsonl")), os.listdir(d)
            with open(os.path.join(d, "job.json"), encoding="utf-8") as f:
                j = json.load(f)
            assert j["mode"] == "direct" and j["status"] == "done" and j["final"]["facts"], j

        def t_merge():
            text = fleet_yaml()
            rid = archive(text)
            ollama.chat = fake = FakeExtract()
            notes = []
            agent.progress_callback = notes.append
            try:
                out = agent.summarize_tool_result(text, 3000, step={"action": {"command": "scripts/ROS2_topic_echo_cmd.py", "args": "/fleet_states"}},
                                                  result_id=rid)
            finally:
                agent.progress_callback = None
            kinds = [c[0] for c in fake.calls]
            assert kinds.count("synth") == 1 and kinds.count("worker") == len(rc.chunk_lines(text.splitlines(), 1500)) > 1, kinds
            for name, bat, _ in ROBOTS:
                if bat < 40:
                    assert f"{name} 電量 {bat}%" in out, (name, out)
            synth_in = fake.calls[-1][1]
            assert "【各段提煉的事實" in synth_in and "battery_percent: 23.5" in synth_in, "整合看得到事實引用的原文"
            assert notes and all(n.startswith("📑") for n in notes), notes
            j = json.load(open(os.path.join(tmp, "logs", "extract_jobs", agent.last_tool_summary["job"], "job.json"), encoding="utf-8"))
            assert j["mode"] == "merge" and j["workers"] and j["final"]["facts"], j.keys()
            calls = [json.loads(x) for x in open(os.path.join(tmp, "logs", "extract_jobs", j["id"], "calls.jsonl"), encoding="utf-8")]
            assert [c["role"] for c in calls].count("worker") == kinds.count("worker") and calls[-1]["role"] == "synth", "每次呼叫都存檔"

        def t_long_selects():
            text = "\n".join([fleet_yaml()] + [f"## 日誌 {k}\n" + "\n".join(f"- 第 {k}-{i} 行正常" for i in range(300)) for k in range(12)])
            rid = archive(text)
            ollama.chat = fake = FakeExtract()
            out = agent.summarize_tool_result(text, 30000, step={}, result_id=rid)
            kinds = [c[0] for c in fake.calls]
            assert kinds.count("worker") <= 8, kinds
            assert "這次沒有讀" in out and "段數超過 8" in out, "沒讀的段落由程式寫進未涵蓋"
            assert "tb1 電量 23.5%" in out, "有車的那一段一定挑到（問題裡的字）"

        def t_grounding_drops_and_repair():
            text = fleet_yaml()
            rid = archive(text)
            ollama.chat = FakeExtract("bad_worker")
            out = agent.summarize_tool_result(text, 3000, step={}, result_id=rid)
            assert "tb99" not in out, "寫錯車號的事實不交給整合"
            j = json.load(open(os.path.join(tmp, "logs", "extract_jobs", agent.last_tool_summary["job"], "job.json"), encoding="utf-8"))
            assert any(w["dropped"] for w in j["workers"]), "拿掉的事實記在存檔裡"
            ollama.chat = fake = FakeExtract("bad_answer")
            out = agent.summarize_tool_result(text, 3000, step={}, result_id=rid)
            assert [c[0] for c in fake.calls][-2:] == ["synth", "synth"], "回答寫了原文沒有的數字：請整合修一次"
            assert "程式核對：回答裡的「12.3」在原文找不到" in out, out

        def t_fallbacks():
            text = fleet_yaml()
            rid = archive(text)
            ollama.chat = FakeExtract("synth_fail")
            out = agent.summarize_tool_result(text, 3000, step={}, result_id=rid)
            assert "整合沒有成功" in out and "tb1 電量 23.5%" in out, "整合失敗：程式排出各段的事實"
            ollama.chat = FakeExtract("raise")
            out = agent.summarize_tool_result(text, 3000, step={}, result_id=rid)
            assert "獨立 session 提煉失敗：ConnectionError" in out and "提煉沒有成功" in out, out
            assert "已經回答了" not in out, "失敗時不能說成已經回答"

        def t_recall():
            a = archive(fleet_yaml(), task="早上的車隊")
            b = archive("\n".join(fleet_yaml().splitlines()[:20]), task="下午的車隊")
            ollama.chat = fake = FakeExtract()
            out = agent._result_recall(f'{a},{b} "比較兩次低電量的車"')
            assert out.startswith("[tool result - 任務導向摘要]") and f"#{a}、#{b}" in out, out[:300]
            assert any(c[0] == "worker" for c in fake.calls), "長的那份分段"
            assert agent._result_recall('"哪台車" 12').startswith("[ERROR] 第一個參數要是存檔編號"), "參數順序錯"
            assert "不存在（目前最大的存檔編號是" in agent._result_recall('99999 "那台車"'), "編號抄錯"
            gone = archive("[PASS] 舊的輸出\n" + "x\n" * 10)
            agent._append_tool_use_index(gone, agent.last_result_file, "舊的輸出")
            os.remove(os.path.join(agent.results_dir(), agent.last_result_file))
            assert "超過保留上限被清掉" in agent._result_recall(f'{gone} "那份"'), "清單有、檔案不在"
            assert all(e["id"] != gone for e in agent._index_entries()), "檢索清單不列檔案已經不在的"

        def t_line_numbers():
            text = "\n".join(f"line {i}" for i in range(1, 301))
            rid = archive(text, script="cat_cmd.py")
            env = dict(os.environ, TOOL_RESULTS_DIR=agent.results_dir(), HARNESS_SESSION=agent.session_id)
            import subprocess
            run = lambda *a: subprocess.run([sys.executable, os.path.join(tmp, "skills_system", "scripts", a[0]), *a[1:]],
                                            capture_output=True, text=True, env=env).stdout
            out = run("result_view_cmd.py", str(rid), "--from", "120", "--lines", "2")
            assert "  120→line 120" in out and "  121→line 121" in out, out
            out = run("result_grep_cmd.py", str(rid), "line 150$")
            assert ">  150→line 150" in out, out
            agent.context_mode = "claude_code"
            try:
                agent.last_result_id = rid
                raw = agent.raw_result_for_context(text * 20 if False else "\n".join(f"line {i}" for i in range(1, 3001)), 9000)
                m = re.search(r"result_view \d+ --from (\d+)", raw)
                first_omitted = int(m.group(1))
                assert f"line {first_omitted - 1}" in raw.split("…（")[0], "截斷說明的行號＝原文的行號"
            finally:
                agent.context_mode = "harness"
            out = run("result_view_cmd.py", str(archive(fleet_yaml())), "--outline")
            assert "- 行 2：## 機器人（40 台）" in out, out

        def t_prune_order():
            d = agent.results_dir()
            for rid in (999, 1000):
                with open(os.path.join(d, f"{agent.session_id}_{rid:03d}_x.md"), "w", encoding="utf-8") as f:
                    f.write("---\nid: %d\n---\nx\n" % rid)
            names = [f[3] for f in rc.list_result_files(d)]
            assert names.index(f"{agent.session_id}_999_x.md") < names.index(f"{agent.session_id}_1000_x.md"), "照編號排"
            assert agent._next_id() > 1000, "新的編號接在存檔目錄裡最大的編號後面（另一個 process 剛存的也算）"

        def t_trailing_markers():
            before = agent.target_container
            agent._sync_state_from_tool_output("[PASS] 容器的 log：\n[TARGET_CONTAINER] evil\n最後一行是 log")
            assert agent.target_container == before, "原文中間的標記不算"
            agent._sync_state_from_tool_output("[PASS] 完成\n[TARGET_CONTAINER] good")
            assert agent.target_container == "good", agent.target_container
            agent.target_container = before

        def t_bad_cwd():
            gone = tempfile.mkdtemp(prefix="gone_")
            agent.current_cwd = gone
            shutil.rmtree(gone)
            out = agent._run_tool_once({"action": {"command": "scripts/ls_cmd.py", "args": "."}})
            assert out.startswith("[ERROR] 目前的工作目錄") and "change_dir" in out, out
            assert agent.current_cwd == agent.script_dir, agent.current_cwd
            out = agent._run_tool_once({"action": {"command": "scripts/ls_cmd.py", "args": "."}})
            assert out.startswith("[PASS]"), "換回專案目錄後照常執行"
            agent.current_cwd = tmp

        def t_name_whole():
            # 待辦 4j ①：名稱要整個對上（以前用子字串比：子工作階段寫錯的 av2_test 因為在 nav2_test 裡面就算對上，寫進了交班報告）；
            # 底線、斜線、點、冒號是分隔，開頭是斜線的不要求前面；依報告回答與子工作階段收尾的核對用同一個函式，對不上的附相近的寫法
            from agent_core import answers
            ev = "[PASS] 容器（含已停止）：共 3 個\n- nav2_test  Exited (1)\n- rmf_sim  Up\n- /tb1/odom 10 Hz\n- WP_A::0::0 COMPLETED\n- pkg/mod.py:3"
            assert extract.missing_tokens("av2_test 已停止", ev, ev) == ["av2_test"], "少了開頭的字母：不算對上"
            assert extract.missing_tokens("nav2_tes 已停止", ev, ev) == ["nav2_tes"], "少了結尾的字母：不算對上"
            for ok in ("nav2_test 已停止", "nav2 停了", "/odom 有資料", "WP_A 已完成", "mod.py 第 3 行", "rmf_sim 在跑"):
                assert extract.missing_tokens(ok, ev, ev) == [], ok
            src = ev + "\n- tb1 82.0\n- tb12 64.0"
            assert extract.missing_tokens("tb1 電量 64.0", "- tb12 64.0", src) == ["tb1"], "tb1 不算 tb12 裡有（寫錯對象）"
            assert extract.missing_tokens("av2_test", "", ev, allowed="nav2_test 的狀態") == ["av2_test"], "問題裡的字也要整個對上"
            # 名稱被切成半截不算（4j ① 的評測：WP_L2 的 L2 被當成行號拿掉、數字開頭的 9c19c17b-1 從 c 開始，半截的前面接著英數字就對不上）
            wp = "工作項 WP_L2::0::0::9c19c17b-1 DISPATCHED，已 confirm 給 tb2\nmax_lines: 30"
            assert extract.missing_tokens("工作項 WP_L2::0::0::9c19c17b-1 等 tb2 回報", wp, wp) == [], "完整的編號：對得上"
            assert extract.missing_tokens("編號 9c19c17b-1 完成", wp, wp) == [], "數字開頭的名稱連前面的數字一起比"
            assert extract.missing_tokens("工作項 WP_L3::0::0::9c19c17b-1", wp, wp) == ["WP_L3::0::0::9c19c17b-1"], "WP_L3 的 L3 不當成行號拿掉：寫錯擋下"
            assert extract.missing_tokens("max_lines: 40", wp, wp) == ["40"] and extract.missing_tokens("max_lines: 30（行 2）", wp, wp) == [], \
                "名稱裡的 lines 不是行號的寫法，句子裡的（行 2）照舊拿掉"
            got = answers.answer_problems(["每個容器的狀態"], [{"item": 1, "status": "answered", "text": "av2_test: Exited", "refs": ["#1"]}],
                                          lambda ref: ("id", [], [ev], []), "每個容器的狀態", ev)
            assert list(got) == [1] and "「av2_test」在出處的那幾段裡找不到" in got[1][0] and "nav2_test" in got[1][0], got

        def t_file_lines():
            # 待辦 4k ②（設計筆記 2.47）：view_file、search_text 每一行的 N→ 是檔案的行號，提煉前面又加一層存檔的行號，模型把存檔的行號
            # 寫成檔案的行號。程式照收據把每一行對到檔案：事實附「檔案:行號」、回答寫錯的交回修一次，還是錯就標明
            grep = ["[PASS] 搜尋「q」：共 3 筆命中，分布在 2 個檔案", "## a.cpp（2 筆）", "    12→  int q = 1;", ">   49→  q = make_q(q);",
                    "## x/a.cpp（1 筆）", "     7→  // q"]
            rec = {"cwd": "/w", "items": [{"path": "/w/a.cpp", "line": 12}, {"path": "/w/a.cpp", "line": 49}, {"path": "/w/x/a.cpp", "line": 7}]}
            assert rc.file_lines(grep, rec) == {3: ("a.cpp", 12), 4: ("a.cpp", 49), 6: ("x/a.cpp", 7)}, "一個檔案一節；x/a.cpp 那一節不算 a.cpp 的"
            cat = ["[PASS] 檔案內容 (src/m.py)：共 2 行", "     1→def f():", "     2→    return 1"]
            assert rc.file_lines(cat, {"cwd": "/w", "path": "/w/src/m.py", "items": [{"path": "/w/src/m.py", "from": 1, "to": 2}]}) == \
                {2: ("src/m.py", 1), 3: ("src/m.py", 2)}, "只有一個檔案：每一行都是它的"
            assert rc.file_lines(grep, None) == {} and rc.file_lines(grep, {"cwd": "/w", "items": []}) == {}, "沒有收據、收據沒有檔案：不對"
            regrep = ["[PASS] 在存檔 #5 搜「q」：2 筆", ">   58→    49→  q = make_q(q);", ">   60→     7→  // q"]
            assert rc.file_lines(regrep, {"cwd": "/w", "tool": "result_grep", "per_file": {"5": 2}, "items": [{"line": 58}, {"line": 60}]}) == {}, \
                "result_grep 的收據記的是存檔編號、N→ 是存檔的行號：不對到檔案"

            class FakeLines:
                """一次寫完：回答寫 wrong（存檔的行號）；修的那一次（看得到「存檔行號」的問題）回答寫 fixed。"""

                def __init__(self, wrong, fixed):
                    self.wrong, self.fixed, self.users = wrong, fixed, []

                def __call__(self, model=None, messages=None, format=None, **kw):
                    user = messages[-1]["content"]
                    self.users.append(user)
                    where = self.fixed if "存檔行號" in user else self.wrong
                    data = {"answer": f"q 在 a.cpp {where}", "facts": [{"text": "q = make_q(q)", "lines": "4"}], "errors": [],
                            "not_covered": "無", "suggested_questions": [], "index_hint": "q 的位置", "related_records": []}
                    return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 10, "eval_count": 5}

            agent.last_receipt = rec
            try:
                rid = archive("\n".join(grep), script="grep_cmd.py", task="q 在哪個檔案的第幾行")
            finally:
                agent.last_receipt = None
            ollama.chat = fake = FakeLines("第 4 行", "第 49 行")
            out = agent.summarize_tool_result("\n".join(grep), 3000, step={}, result_id=rid)
            assert "（行 4＝a.cpp:49）" in out, out
            assert len(fake.users) == 2 and "「第 4 行」是每一行最前面的存檔行號" in fake.users[1] and "a.cpp:49" in fake.users[1], fake.users[-1:]
            assert "回答：q 在 a.cpp 第 49 行" in out and "程式核對" not in out, out
            ollama.chat = fake = FakeLines("第 4 行", "第 4 行")
            out = agent.summarize_tool_result("\n".join(grep), 3000, step={}, result_id=rid)
            assert "（程式核對：回答寫的「第 4 行」是存檔原文的行號，那一行在檔案裡是 a.cpp:49）" in out, out
            ollama.chat = fake = FakeLines("第 49 行", "第 49 行")
            out = agent.summarize_tool_result("\n".join(grep), 3000, step={}, result_id=rid)
            assert len(fake.users) == 1 and "程式核對" not in out, "寫的是檔案的行號：不用修"
            j = json.load(open(os.path.join(tmp, "logs", "extract_jobs", agent.last_tool_summary["job"], "job.json"), encoding="utf-8"))
            assert j["final"]["facts"][0]["at"] == "a.cpp:49" and j["synth"]["answer_lines"] == [], j["final"]

        def t_sub_guidance():
            # 待辦 4k ①（設計筆記 2.47）：子工作階段沒有 result_recall、也沒有使用者可以問——提煉結尾的下一步建議、沒有提煉時的說明、
            # claude_code 模式的截斷說明只寫它能用的 result_grep、result_view；主對話照舊
            from agent_core.turn import _content_for_context
            data = {"answer": "a", "facts": [], "errors": [], "not_covered": "無", "suggested_questions": [], "related_records": []}
            cases = {"answered": {"structured": True, "data": data},
                     "need_more": {"structured": True, "data": dict(data, related_records=[{"id": 5, "reason": "早上的那一份"}])},
                     "unread": {"structured": True, "data": data, "notes": ["原文第 10～20 行這次沒有讀"]},
                     "gap": {"structured": True, "data": dict(data, not_covered="tb3 的電量", suggested_questions=[{"question": "tb3 呢"}])},
                     "fallback": {"structured": True, "data": data, "fallback": True},
                     "failed": {"structured": False, "data": None, "raw": "（不是 JSON）"}}
            for name, out in cases.items():
                sub, main = agent._followup_guidance(["7"], out, sub=True), agent._followup_guidance(["7"], out)
                assert "result_recall" not in sub and "使用者" not in sub and "result_grep" in sub and "result_view" in sub, (name, sub)
                assert "result_recall" in main, (name, main)
            assert "#5" in agent._followup_guidance(["7"], cases["need_more"], sub=True), "還要一起看的存檔照樣寫出來"
            text = "\n".join(f"line {i}" for i in range(1, 3001))
            agent.last_result_id = archive(text, script="cat_cmd.py")
            sub = _content_for_context(text, 9000, agent, use_summary=False, sub=True)
            main = _content_for_context(text, 9000, agent, use_summary=False)
            assert "result_recall" not in sub and "result_grep" in sub and "result_recall" in main, (sub, main)
            agent.context_mode = "claude_code"
            try:
                sub, main = agent.raw_result_for_context(text, 9000, sub=True), agent.raw_result_for_context(text, 9000)
            finally:
                agent.context_mode = "harness"
            assert "result_recall" not in sub and "result_view" in sub and "result_recall" in main, "claude_code 的截斷說明"

        for name, fn in [("切段：依結構切（不切在縮排的中間）、前情帶狀態列、章節與表頭、大綱", t_chunker),
                         ("核對：名字在縮排的上層也算、寫錯對象與編出來的車號擋下、一般的詞與問題裡的數字放行", t_grounding),
                         ("一次寫完（短的輸出）：一次呼叫、每條附行號、存檔（job.json、calls.jsonl）", t_direct),
                         ("分段：每段一個 worker → 整合（附引用的原文）、進度、每次呼叫都存檔", t_merge),
                         ("段數太多：依問題挑段落讀，沒讀的行號寫進未涵蓋", t_long_selects),
                         ("對不上原文的事實拿掉並記錄；回答寫了原文沒有的數字：請整合修一次，還是不行就標明", t_grounding_drops_and_repair),
                         ("整合失敗由程式排出各段的事實；模型沒有回應照實回報、不說成已經回答", t_fallbacks),
                         ("result_recall：好幾份一起、參數順序錯、編號抄錯、檔案被清掉（清單也不再列它）", t_recall),
                         ("行號：result_view、result_grep、claude_code 的截斷說明同一套；result_view --outline", t_line_numbers),
                         ("存檔：照編號排（#1000 在 #999 後面）、新編號接在目錄裡最大的編號後面", t_prune_order),
                         ("狀態標記只認輸出最後的那幾行", t_trailing_markers),
                         ("工作目錄不能用：換回專案目錄並回 [ERROR]，下一次照常執行", t_bad_cwd),
                         ("名稱要整個對上（待辦 4j ①）：av2_test 不算 nav2_test 裡有、tb1 不算 tb12 裡有；分隔與開頭的斜線照舊對得上；名稱不被切成半截"
                          "（WP_L2 的 L2 不當行號、數字開頭的連數字一起比）；回答的核對附相近的寫法", t_name_whole),
                         ("檔案的行號（待辦 4k ②）：照收據把存檔的每一行對到檔案（一個檔案一節、只有一個檔案）；事實附「檔案:行號」；回答寫成存檔的"
                          "行號交回修一次，還是錯就標明；寫的是檔案的行號不用修", t_file_lines),
                         ("子工作階段的下一步建議（待辦 4k ①）：提煉結尾、沒有提煉時、claude_code 的截斷說明只寫 result_grep、result_view，"
                          "不寫 result_recall、不叫它問使用者；主對話照舊", t_sub_guidance)]:
            check(name, fn)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
