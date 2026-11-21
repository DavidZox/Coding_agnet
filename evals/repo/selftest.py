"""真實專案評測的自我測試（不用模型，幾秒）：核對的比對規則、每一題的答案都答得出來而且每一則事實都必要、常見的錯答會被擋、
真實回覆（人看過的）維持原來的判斷、answers.json 跟快照算出來的一樣（快照不在就略過）、跑評測時碰不到真的容器與調度系統、主機的家目錄、
階段驗證（phase_check 的 repo）怎麼合成好幾次的結果、怎麼跟基準比。

    python3 evals/repo/selftest.py
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import checks      # noqa: E402
import questions   # noqa: E402
import run         # noqa: E402
import snapshot    # noqa: E402

ANSWERS = questions.load()
BY_ID = {q["id"]: q for q in ANSWERS["questions"]}


class Skip(Exception):
    pass


def _ok(q, reply):
    return checks.score(q, reply)["passed"]


def t_match_rules():
    def has(text, *alts):
        return bool(checks.positions(text, list(alts)))
    assert has("總共 28 次", "28") and not has("128 次", "28") and not has("2.8", "28") and not has("28.5", "28")
    assert has("檔案的第 L178 行", "178")
    assert not has("odom_frame_id", "odom") and has("odom_frame_id 預設 odom", "odom")
    assert not has("fleet_registry.py", "registry.py") and has("registry/registry.py:80", "registry.py")
    assert not has("/scan_merged", "/scan") and not has("/front/scan", "/scan") and has("訂閱 `/scan`", "/scan")
    assert has("回到 idle", "IDLE") and has("繼續等待", "繼續等")
    same_line = {"all": [["adapter_node.py"], ["2"]], "line": True}
    assert checks.item_ok("adapter_node.py：2 次", same_line)
    assert not checks.item_ok("x.py：2 次\nadapter_node.py：3 次", same_line), "隔壁一行的數字不能算"
    by_file = lambda f, n: {"all": [[f], [n]], "file": True}     # noqa: E731
    listed = "定義：\n- 檔案：A.py\n- 行號：第 99 行\n呼叫：\n- 檔案：B.py\n  - 第 25 行\n  - 第 106 行\n- 檔案：C.py\n  - 第 653 行"
    assert checks.item_ok(listed, by_file("A.py", "99")) and checks.item_ok(listed, by_file("B.py", "106"))
    assert checks.item_ok(listed, by_file("C.py", "653")) and checks.item_ok("在第 82 行（B.py）呼叫", by_file("B.py", "82"))
    assert not checks.item_ok(listed, by_file("B.py", "653")) and not checks.item_ok(listed, by_file("A.py", "106")), "下一個檔案的數字不能算"
    near = {"all": [["TSK-S08"], ["繼續等"]], "near": 10}
    assert checks.item_ok("TSK-S08：繼續等", near) and not checks.item_ok("TSK-S08" + "。" * 30 + "繼續等", near)


def _reply_from(items):
    """每一則事實寫成一行（每一組用第一個照字面的寫法；re: 開頭的是比對用的正規表示式）。"""
    return ["：".join(next(a for a in grp if not a.startswith("re:")) for grp in it["all"]) for it in items]


def t_every_question_answerable():
    for q in ANSWERS["questions"]:
        lines = _reply_from(q["items"])
        sc = checks.score(q, "\n".join(lines))
        assert sc["passed"], (q["id"], sc)
        for k in range(len(lines)):               # 每一則事實都必要：少了哪一行都不能過
            assert not _ok(q, "\n".join(lines[:k] + lines[k + 1:])), (q["id"], "少了也過", q["items"][k]["label"])
        for k, it in enumerate(q["items"]):       # 數字寫錯（加 1）就不能過
            if any(re.fullmatch(r"\d+(?:\.\d+)?", a) for grp in it["all"] for a in grp):
                bad = re.sub(r"(?<![\d.])(\d+)((?:\.\d+)?)(?![\d.])", lambda m: str(int(m.group(1)) + 1) + m.group(2), lines[k])
                assert not _ok(q, "\n".join(lines[:k] + [bad] + lines[k + 1:])), (q["id"], "數字錯了也過", bad)


def t_known_wrong_answers():
    q = BY_ID["cnt_rmf_publishers"]
    good = "\n".join(_reply_from(q["items"]))
    assert _ok(q, good)
    wrong_total = good.replace(f"28：{questions.TOTAL[0]}", f"41：{questions.TOTAL[0]}") + "\n整個套件總共 41 次"
    sc = checks.score(q, wrong_total)
    assert not sc["passed"] and sc["forbidden"], sc
    q = BY_ID["cross_rf2o_runtime"]
    code_default = "rf2o 的里程計發到 /odom_rf2o，頻率 10 Hz，會發 TF（publish_tf: true），robot_localization 的 EKF 用它。"
    assert not _ok(q, code_default)
    assert _ok(q, "發到 /rf2o_odom（launch 覆寫了程式的預設 /odom_rf2o）\n頻率 20 Hz\npublish_tf: False，不發 TF\nrobot_localization 的 EKF（ekf.yaml 的 odom1）用它")
    q = BY_ID["py_speed_limit"]
    lines = _reply_from(q["items"])
    assert not _ok(q, "\n".join(lines[:-1])), "少列一個呼叫的地方不能過"
    q = BY_ID["doc_task_confirm"]
    assert _ok(q, "TSK-S08：不同 task_id 的 confirm，狀態不變，繼續等。\nTSK-S06：同一筆的 authorize 又來，重發 yes，不重新計時。")
    q = BY_ID["cpp_laser_qos"]
    where = q["items"][0]["label"]
    assert _ok(q, f"{where}：rclcpp::QoS(rclcpp::KeepLast(1)).best_effort().durability_volatile()"), "程式裡的寫法 durability_volatile 也算 volatile（待辦 4j ③）"
    assert not _ok(q, f"{where}：KeepLast(1)、best_effort，durability 是 transient_local"), "durability 答錯不能過"
    assert checks.score(q, "TSK-S08：繼續等\nTSK-S06：重發 yes，不重新計時", guards=1)["forbidden"], "碰到確認關卡要算錯"


def t_real_replies():
    """2026-11-18 第一次試跑與最終量測的真實回覆（人看過、確認對錯）：核對要維持這些判斷。"""
    with open(os.path.join(HERE, "fixtures", "replies_20261118.json"), encoding="utf-8") as f:
        cases = json.load(f)["replies"]
    for c in cases:
        sc = checks.score(BY_ID[c["id"]], c["reply"])
        got_ok = [i["label"] for i in sc["items"] if i["ok"]]
        assert sc["passed"] == c["passed"] and got_ok == c["ok"], (c["id"], c["model"], c["why"], got_ok)


def t_answers_shape():
    qs = ANSWERS["questions"]
    assert ANSWERS["commit"] == snapshot.COMMIT and ANSWERS["digest"] == snapshot.DIGEST
    assert len({q["id"] for q in qs}) == len(qs) == 30
    for kind in questions.KINDS:
        assert [q["set"] for q in qs if q["kind"] == kind].count("main") == 5, kind
        assert [q["set"] for q in qs if q["kind"] == kind].count("holdout") == 1, kind
    assert all(q["items"] and all(it["all"] and all(grp for grp in it["all"]) for it in q["items"]) for q in qs)
    no_literal = [(q["id"], it["label"]) for q in qs for it in q["items"] + q["forbid"] for grp in it["all"]
                  if all(a.startswith("re:") for a in grp)]
    assert not no_literal, f"每一組寫法都要有一個照字面的（給人看，也給自我測試組回覆）：{no_literal}"
    assert [q["id"] for q in qs] == [q["id"] for q in questions.QUESTIONS], "answers.json 跟題目的順序或題數不一樣"


def t_answers_match_snapshot():
    err = snapshot.problem()
    if err:
        raise Skip(err)
    tmp = tempfile.mkdtemp(prefix="repo_selftest_")
    try:
        src = snapshot.extract(tmp)
        try:
            open(os.path.join(src, "fih_rmf_system", "setup.py"), "a").close()
            raise AssertionError("快照解開後應該是唯讀的")
        except PermissionError:
            pass
        assert not os.path.lexists(os.path.join(src, "amr_base_sw", "tool", "recordings")), "指到快照外面的連結不能解開"
        got = questions.compute_all(src)
    finally:
        snapshot.remove(tmp)
    assert got == ANSWERS["questions"], "answers.json 跟快照算出來的不一樣（python3 evals/repo/questions.py --write）"


def t_runner_safety():
    env = run.worker_env("m", "/tmp/x", "/tmp/src")
    assert env["OPS_FS_ROOT"] == "/tmp/src" and env["EVAL_MODEL"] == "m"
    for k, v in run.UNREACHABLE.items():
        assert env[k] == v and ":9" in v, (k, v)
    names = set()
    for path in glob.glob(os.path.join(PROJECT, "skills_system", "scripts", "*.py")):
        with open(path, encoding="utf-8") as f:
            names |= set(re.findall(r"[\"']([A-Z][A-Z0-9_]*_URL)[\"']", f.read()))
    assert names and names <= set(run.UNREACHABLE), f"技能讀的外部系統位址沒有全部指到不存在的地方：{sorted(names - set(run.UNREACHABLE))}"
    sc = run.scenario(BY_ID["py_fleet_msg"])
    assert sc["guard"] == "deny" and sc["turns"] == [{"user": BY_ID["py_fleet_msg"]["question"]}]
    # 家目錄（待辦 4f ③）：harness 副本旁邊的空目錄——真的跑一次 `cd ~`，停在那裡，不是主機的家目錄，也不在副本裡（副本裡有題目與答案）
    tmp = tempfile.mkdtemp(prefix="repo_selftest_")
    try:
        env = run.worker_env("m", tmp, "/tmp/src")
        home = env["HOME"]
        assert home == tmp + "_home" and not home.startswith(tmp + os.sep), home
        assert os.path.realpath(home) != os.path.realpath(os.path.expanduser("~")), "不能是主機的家目錄"
        os.makedirs(home)
        r = subprocess.run([sys.executable, os.path.join(PROJECT, "skills_system", "scripts", "cd_cmd.py"), "~"], cwd=tmp, env=env,
                           capture_output=True, text=True, timeout=60)
        assert f"[CWD_CHANGED] {home}" in r.stdout, r.stdout + r.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp + "_home", ignore_errors=True)


def t_rescore():
    q = BY_ID["doc_nav_stop"]
    r = {"id": q["id"], "kind": q["kind"], "set": q["set"], "package": q["package"], "model": "m", "guards": 0, "tool_calls": [],
         "wall_seconds": 1.0, "reply": "規格書寫的（LNV-F063）：轉到 IDLE，不會進行回報。",
         "score": {"passed": False, "checks_passed": 0, "checks_total": 2, "items": [], "forbidden": []}}
    with tempfile.TemporaryDirectory(prefix="repo_rescore_") as d:
        with open(os.path.join(d, "runs.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        assert run.rescore(d)[0]["score"]["passed"]
        with open(os.path.join(d, "runs.jsonl"), encoding="utf-8") as f:
            assert json.loads(f.readline())["score"]["passed"], "重新計分要寫回 runs.jsonl"
        with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
            report = f.read()
        assert report.startswith("# 真實專案評測：m") and "重新計分" in report and "✅" in report, report


def t_layers():
    """沒過的每一項分到第一個沒出現的層（原文 → 事實 → 下一層的回答 → 最後的回覆），一題取最前面的；過了的不列；交給領域的子目標列出來。"""
    import layers
    q = {"id": "lx", "items": [{"label": l, "all": [[w]]} for l, w in (("A", "alpha"), ("B", "beta"), ("C", "gamma"), ("D", "delta"), ("E", "epsil"))]}
    with tempfile.TemporaryDirectory(prefix="repo_layers_") as d:
        log = os.path.join(d, "logs", "lx")
        os.makedirs(os.path.join(log, "tool_results"))
        os.makedirs(os.path.join(log, "extract_jobs", "j1"))
        os.makedirs(os.path.join(log, "sub_jobs", "j1"))
        for name, text in (("001_grep.md", "---\nid: 1\n---\nalpha beta delta epsil"), ("002_domain_repo_analysis.md", "---\nid: 2\n---\nalpha beta gamma"),
                           ("index.md", "gamma")):
            with open(os.path.join(log, "tool_results", name), "w", encoding="utf-8") as f:
                f.write(text)
        with open(os.path.join(log, "extract_jobs", "j1", "job.json"), "w", encoding="utf-8") as f:
            json.dump({"final": {"answer": "", "facts": [{"text": "beta"}, {"text": "x.py:3：delta"}]}}, f)
        with open(os.path.join(log, "sub_jobs", "j1", "job.json"), "w", encoding="utf-8") as f:
            json.dump({"answers": [{"item": 1, "text": "delta"}, {"item": 2, "text": "epsil"}]}, f)
        fail = {"id": "lx", "set": "main", "model": "m", "reply": "epsil", "tool_calls": [{"domain": "repo_analysis", "goal": "g", "items": ["i"]}, {"skill": "x"}],
                "score": {"passed": False, "items": [{"ok": False}] * 5}}
        with open(os.path.join(d, "runs.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(fail) + "\n" + json.dumps(dict(fail, id="ok", score={"passed": True})) + "\n")
        out = layers.trace(d, by_id={"lx": q})
    assert len(out) == 1, out
    got = {x["label"]: x["guess"] for x in out[0]["items"]}
    assert got == {"A": "看", "B": "回答・下一層", "C": "找", "D": "回答・主對話", "E": "評測或算"}, got
    assert out[0]["guess"] == "找" and out[0]["dispatch"] == [{"domain": "repo_analysis", "goal": "g", "items": ["i"]}], out[0]


def t_final_reply():
    out = {"turns": [{"steps": [{"reply": "我先搜尋", "action": "EXECUTE: scripts/grep_cmd.py x"},
                                {"reply": "答案在這裡", "action": None}]}], "replies": ["我先搜尋", "答案在這裡"]}
    assert checks.final_reply(out) == "答案在這裡"
    out = {"turns": [{"steps": [{"reply": "還在查", "action": "EXECUTE: scripts/grep_cmd.py x"}]}], "replies": ["還在查"]}
    assert checks.final_reply(out) == "還在查"
    assert checks.final_reply({}) == ""


def t_phase_baseline():
    """階段驗證（phase_check --model 的 repo）：好幾次的結果合成一份、每一題的通過率與每一次的主要組通過數跟基準比。"""
    sys.path.insert(0, os.path.join(PROJECT, "evals"))
    try:
        import phase_check as pc
    finally:
        del sys.path[0]
    with tempfile.TemporaryDirectory(prefix="repo_phase_") as root:
        dirs = []
        for k, rows in enumerate(([("a", "main", True), ("b", "main", False), ("h", "holdout", True)],
                                  [("a", "main", True), ("b", "main", True), ("h", "holdout", False)])):
            d = os.path.join(root, f"2026111{k}_000000_repo_m_all_phase{k + 1}")
            os.makedirs(d)
            with open(os.path.join(d, "runs.jsonl"), "w", encoding="utf-8") as f:
                f.writelines(json.dumps({"id": i, "set": st, "model": "m", "score": {"passed": ok}}) + "\n" for i, st, ok in rows)
            dirs.append(d)
        assert pc.classify(dirs[0]) == "repo"
        res = pc.from_dirs(dirs)
        assert len(res) == 1 and res[0]["per"] == {"a": [2, 2], "b": [1, 2], "h": [1, 2]} and res[0]["runs"] == [1, 2], res
        assert res[0]["sets"] == {"main": [3, 4], "holdout": [1, 2]}, res[0]["sets"]
        real = pc.load_baseline
        pc.load_baseline = lambda name: {"models": {"m": {"per": {"a": [2, 2], "b": [2, 2]}, "sets": {"main": [4, 4]}, "runs": [2, 2]}}} \
            if name == "repo" else None
        try:
            text, base, verdict, notes = pc.compare(res[0])
        finally:
            pc.load_baseline = real
        assert verdict == "⚠️" and notes[0].startswith("主要組每一次的通過數 1、2，最低的比基準（2、2）低"), notes
        assert "b：1/2（基準 2/2）" in notes and "h：基準裡沒有" in notes and text.startswith("主要 3/4；保留 1/2（主要每一次 1、2）"), (text, notes)


def main():
    tests = [("比對的規則：數字、名稱、topic 的邊界，同一行與距離", t_match_rules),
             ("每一題都答得出來，每一則事實都必要，數字錯了就不過", t_every_question_answerable),
             ("常見的錯答會被擋：整個目錄的總數、只看程式的預設值、少列呼叫、碰到確認關卡", t_known_wrong_answers),
             ("真實回覆（第一次試跑與最終量測、人看過的）維持原來的判斷：引用列裡的分支編號、分行列行號、說法不同", t_real_replies),
             ("answers.json 的形狀：30 題、五種各 5＋1、跟快照的版本一致", t_answers_shape),
             ("answers.json 跟快照算出來的一樣；快照唯讀、不解開指到外面的連結", t_answers_match_snapshot),
             ("跑評測時碰不到真的容器與調度系統、主機的家目錄；確認關卡一律拒絕", t_runner_safety),
             ("核對改了之後用存下來的回覆重新計分（不跑模型），寫回 runs.jsonl 與報表", t_rescore),
             ("沒過的分層（步驟 0 的方法）：每一項到第一個沒出現的層，一題取最前面的，列出交給領域的子目標", t_layers),
             ("最後的回覆：最後一步沒有動作的那則", t_final_reply),
             ("階段驗證：好幾次的結果合成一份，每一題與每一次的主要組通過數跟基準比", t_phase_baseline)]
    passed = skipped = 0
    failed = []
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"✅ {name}")
        except Skip as e:
            skipped += 1
            print(f"⏭️ {name}：略過（{e}）")
        except Exception as e:
            failed.append((name, traceback.format_exc()))
            print(f"❌ {name}：{e}")
    for name, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{passed}/{len(tests) - skipped} 通過" + (f"，{skipped} 個略過" if skipped else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
