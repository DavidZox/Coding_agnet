"""多步驟維運（ops_plan／ops_run）與維運技能的離線自我測試：假的 ollama.chat 照劇本回答，不需要 Ollama、不需要 docker。

    python3 evals/ops/selftest.py

測的是 harness 的程式把關（不是模型能力；模型能力用 evals/ops/run.py 量）：
- 🧭 多步驟維運任務（ops_plan／ops_run）：規劃的程式檢查與修正、確認關卡的說明是整份計畫、沒確認不執行、
  每一步一個 worker、計畫沒核准的狀態變更擋下（[DENIED]）、沒用技能就說做完推回去一次、做完由程式檢查、
  檢查沒過換 worker 重試一次、還是不行就停下來（後面的步驟不做）、報告與存檔；
- file_ops（建目錄、寫入含引號的內容、附加、取代要剛好一次、複製不覆蓋、移動、備份、系統目錄不能寫）；
- 新技能的確認關卡：docker_ctl／ROS2_param／rmf_handshake 的唯讀用法不用問、會改變狀態的要問；
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts"]


class FakeOps:
    """規劃 session 依序回 plans；worker（以及主對話）依序回 steps；其他 session 回固定文字。記下每次 worker 收到的訊息。"""

    def __init__(self, plans, steps):
        self.plans, self.steps = list(plans), list(steps)
        self.plan_calls, self.worker_calls, self.worker_msgs = 0, 0, []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = sorted((format or {}).get("properties", {})) if isinstance(format, dict) else []
        if "understanding" in props and "items" in props:
            self.plan_calls += 1
            data = self.plans.pop(0) if self.plans else {"understanding": "", "summary": "", "items": [], "report": ""}
        elif props == ["done", "summary"]:
            self.worker_calls += 1
            data = self.wrapups.pop(0) if getattr(self, "wrapups", None) else {"done": False, "summary": "沒做完"}
        elif "action" in props:
            self.worker_calls += 1
            self.worker_msgs.append(list(messages or []))
            data = self.steps.pop(0) if self.steps else {"thought": "", "reply": "完成", "action": None}
        else:
            return {"message": {"content": "（摘要）"}, "prompt_eval_count": 100, "eval_count": 20}
        return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 100, "eval_count": 20}


def step(cmd, args="", reply="執行中"):
    return {"thought": "照做", "reply": reply, "action": {"command": cmd, "args": args}}


def say(reply):
    return {"thought": "回報", "reply": reply, "action": None}


def item(title, goal, skills, changes=False, check=None):
    return {"title": title, "goal": goal, "skills": skills, "changes_state": changes, "check": check}


def plan(*items, summary="測試計畫", report="修改前後的值"):
    return {"understanding": "測試", "summary": summary, "items": list(items), "report": report}


OPS_RUN = {"action": {"command": "scripts/ops_run_cmd.py", "args": ""}}


def scenario(name, fn, results):
    tmp = tempfile.mkdtemp(prefix="ops_selftest_")
    for it in COPY:
        src = os.path.join(PROJECT, it)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(tmp, it), ignore=shutil.ignore_patterns("__pycache__"))
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp, it))
    home = os.path.join(tmp, "ops_home")
    os.makedirs(os.path.join(home, "configs"))
    with open(os.path.join(home, "configs", "nav.yaml"), "w", encoding="utf-8") as f:
        f.write("controller:\n  max_vel_x: 0.26\n  min_vel_x: 0.0\n")
    os.environ["AGENT_PERF_LOG"] = "0"
    sys.path.insert(0, tmp)
    for m in [m for m in sys.modules if m.startswith(("agent_core", "skills_system"))]:
        del sys.modules[m]
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        import ollama
        from agent_core.agent import SkillAgent
        agent = SkillAgent(model="fake")
        agent.current_cwd = home
        fn(agent, ollama, tmp, home)
        results.append((name, True, ""))
        print(f"✅ {name}")
    except Exception as e:
        import traceback
        results.append((name, False, traceback.format_exc()))
        print(f"❌ {name}：{e}")
    finally:
        os.chdir(cwd)
        sys.path.remove(tmp)
        shutil.rmtree(tmp, ignore_errors=True)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 🧭 ops
def t_ops_plan_and_run(agent, ollama, tmp, home):
    first = plan(item("查目前的值", "看 configs/nav.yaml 的 max_vel_x", ["view_file", "no_such_skill"]))
    second = plan(item("查目前的值", "看 configs/nav.yaml 的 max_vel_x 目前的值", ["view_file"]),
                  item("改成 0.5", "把 configs/nav.yaml 的 max_vel_x 從 0.26 改成 0.5", ["scripts/file_ops_cmd.py"],
                       check={"skill": "view_file", "args": "configs/nav.yaml", "expect": r"max_vel_x: 0\.5"}))
    fake = FakeOps([first, second], [
        step("scripts/cat_cmd.py", "configs/nav.yaml"), say("max_vel_x 目前是 0.26"),
        step("scripts/file_ops_cmd.py", 'replace configs/nav.yaml --old "max_vel_x: 0.26" --new "max_vel_x: 0.5"'),
        say("已把 max_vel_x 從 0.26 改成 0.5（原檔已備份）")])
    ollama.chat = fake
    out = agent.run_tool({"action": {"command": "scripts/ops_plan_cmd.py", "args": '"把 max_vel_x 改成 0.5"'}})
    assert out.startswith("[PASS] 計畫（2 步）"), out
    assert fake.plan_calls == 2, "有不存在的技能：要把問題交回規劃 session 修一次"
    d = agent.ops_draft
    assert d["items"][1]["skills"] == ["file_ops"] and d["items"][1]["changes_state"], "腳本路徑換成技能名稱；file_ops 一定會改變狀態"
    assert d["items"][0]["check"] is None and not d["items"][0]["changes_state"]
    guard = agent.guard_check(OPS_RUN)
    assert guard and guard["skill"] == "ops_run" and "會改變狀態的是：第 2 步 改成 0.5" in guard["reason"], guard
    assert "做完檢查：view_file configs/nav.yaml" in agent.guard_prompt_text(guard)
    blocked = agent.run_tool(OPS_RUN, approved=False)
    assert blocked.startswith("[DENIED]") and agent.ops_draft is not None and fake.worker_calls == 0, blocked
    rep = agent.run_tool(OPS_RUN, approved=True)
    assert rep.startswith("[PASS] 計畫執行完成（2/2 步"), rep
    assert "max_vel_x: 0.5" in read(os.path.join(home, "configs", "nav.yaml"))
    assert "檢查：view_file configs/nav.yaml → 有「max_vel_x: 0\\.5」" in rep, rep
    assert "要回報給使用者的重點：修改前後的值" in rep
    w2 = fake.worker_msgs[2]               # 第 2 步的 worker：乾淨的 session，看得到前一步的結果、規格已附上
    assert len(w2) == 2 and "第 1 步「查目前的值」完成：max_vel_x 目前是 0.26" in w2[1]["content"], w2[1]["content"][:600]
    assert "### file_ops" in w2[0]["content"] and "可以用來改變狀態的技能：file_ops" in w2[1]["content"]
    assert agent.ops_draft is None and agent.ops_last["status"] == "done"
    saved = os.listdir(os.path.join(agent.script_dir, "logs", "ops_jobs"))
    assert len(saved) == 1 and json.load(open(os.path.join(agent.script_dir, "logs", "ops_jobs", saved[0])))["status"] == "done"
    assert agent.run_tool(OPS_RUN, approved=True).startswith("[ERROR] 目前沒有待執行的計畫"), "計畫只能執行一次"
    assert agent.guard_check(OPS_RUN) is None, "沒有草稿時不用確認（ops_run 自己回錯誤）"


def t_ops_run_one_action(agent, ollama, tmp, home):
    """ops_run 帶任務：確認關卡先規劃（確認畫面就是計畫）→ 核准 → 執行；同一個任務不重新規劃；規劃失敗不規劃第二次；/guard off 時在執行時規劃。"""
    p = plan(item("改成 0.5", "把 configs/nav.yaml 的 max_vel_x 改成 0.5", ["file_ops"], True,
                  {"skill": "view_file", "args": "configs/nav.yaml", "expect": r"0\.5"}),
             item("確認", "再看一次 configs/nav.yaml", ["view_file"]))
    fake = FakeOps([p], [step("scripts/file_ops_cmd.py", 'replace configs/nav.yaml --old "max_vel_x: 0.26" --new "max_vel_x: 0.5"'),
                         say("已從 0.26 改成 0.5"), step("scripts/cat_cmd.py", "configs/nav.yaml"), say("確認是 0.5")])
    ollama.chat = fake
    act = {"action": {"command": "scripts/ops_run_cmd.py", "args": '"把 max_vel_x 改成 0.5"'}}
    guard = agent.guard_check(act)
    assert guard and guard["skill"] == "ops_run" and "第 1 步 改成 0.5" in guard["reason"] and fake.plan_calls == 1, guard
    assert agent.guard_check(act) and fake.plan_calls == 1, "同一個任務的草稿已經有了：不重新規劃"
    rep = agent.run_tool(act, approved=True)
    assert rep.startswith("[PASS] 計畫執行完成（2/2 步") and fake.plan_calls == 1, rep
    fake = FakeOps([plan(), plan()], [])
    ollama.chat = fake
    bad = {"action": {"command": "scripts/ops_run_cmd.py", "args": '"做一件規劃不出來的事"'}}
    assert agent.guard_check(bad) is None and fake.plan_calls == 1, "規劃失敗：不用確認"
    out = agent.run_tool(bad, approved=False)
    assert out.startswith("[ERROR] 規劃 session 沒有給出可以執行的步驟") and fake.plan_calls == 1, (out[:80], fake.plan_calls)
    agent.guard_enabled = False
    try:
        fake = FakeOps([plan(item("查", "看 configs/nav.yaml", ["view_file"]), item("再查", "看 configs 目錄", ["list_dir"]))],
                       [step("scripts/cat_cmd.py", "configs/nav.yaml"), say("0.5"), step("scripts/ls_cmd.py", "configs"), say("一個檔案")])
        ollama.chat = fake
        out = agent.run_tool({"action": {"command": "scripts/ops_run_cmd.py", "args": '"看一下設定"'}})
        assert out.startswith("[PASS] 計畫執行完成（2/2 步") and fake.plan_calls == 1, out
        fake = FakeOps([plan(item("查", "用 workpackage_status 看 WP_C3", ["workpackage_status"]))], [])
        ollama.chat = fake
        out = agent.run_tool({"action": {"command": "scripts/ops_run_cmd.py", "args": '"WP_C3 為什麼沒開始，先不要修改"'}})
        assert out.startswith("[ERROR] 這個任務一步就做得完，不需要 ops 規劃：直接用 workpackage_status 做"), out
        assert agent.ops_draft is None and fake.worker_calls == 0
    finally:
        agent.guard_enabled = True


def t_ops_denied_retry_stop(agent, ollama, tmp, home):
    p = plan(item("查狀態", "查 nav2 容器的狀態", ["view_file"]),
             item("寫紀錄", "在 notes/out.txt 寫入 hello world", ["file_ops"], True,
                  {"skill": "view_file", "args": "notes/out.txt", "expect": "world"}),
             item("重啟", "重新啟動 nav2", ["docker_ctl"]))
    fake = FakeOps([p], [
        # 第 1 步（只查詢）：想重啟容器 → [DENIED]；沒執行任何技能就說做完 → 推回去一次；之後真的查了才算
        step("scripts/docker_ctl_cmd.py", "restart nav2"), say("沒辦法重啟"), step("scripts/cat_cmd.py", "configs/nav.yaml"),
        say("nav2 的設定檔在 configs/nav.yaml"),
        # 第 2 步：寫錯內容 → 檢查沒過 → 換 worker 重試 → 還是錯 → 停下來
        step("scripts/file_ops_cmd.py", 'write notes/out.txt --text "hello"'), say("寫好了"),
        step("scripts/file_ops_cmd.py", 'write notes/out.txt --text "hello again"'), say("寫好了"),
        # 第 3 步（會改變狀態的 docker_ctl restart 已核准）：這裡只查狀態就回報（沒有 docker，查詢會回錯誤，不影響流程）
        step("scripts/cat_cmd.py", "configs/nav.yaml"), say("已確認")])
    ollama.chat = fake
    assert agent.ops_plan("查 nav2、寫紀錄、重啟").startswith("[PASS]")
    assert agent.ops_draft["items"][2]["changes_state"], "目標寫了「重新啟動」、用的是兩用的 docker_ctl：算會改變狀態"
    rep = agent.run_tool(OPS_RUN, approved=True)
    w1 = fake.worker_msgs[1][-1]["content"]
    assert "[DENIED]" in w1 and "計畫沒有核准這一步改變狀態" in w1, w1
    assert "你還沒有用任何技能" in fake.worker_msgs[2][-1]["content"], "沒用技能就說做完：推回去一次"
    # 第 2 步的檢查兩次都沒過：多半是檢查條件不適用 → 標成「檢查沒過」、不擋下後面的步驟（第 3 步照做）
    assert rep.startswith("[PASS] 計畫的步驟都做了") and "第 2 步做完之後的檢查沒有通過" in rep, rep
    assert "2. ⚠️ 檢查沒過 寫紀錄" in rep and "沒有「world」" in rep, rep
    retry = fake.worker_msgs[6][1]["content"]
    assert "【上一次做這一步沒有成功】你回報完成了，但做完之後的檢查沒有通過" in retry, retry
    assert agent.ops_last["items"][1]["attempts"] == 2 and agent.ops_last["status"] == "unverified"
    assert agent.ops_last["items"][2]["status"] == "done", agent.ops_last["items"][2]


def t_ops_worker_failure_and_scope(agent, ollama, tmp, home):
    p = plan(item("讀設定", "讀 configs/missing.yaml", ["view_file"]), item("回報", "整理讀到的設定", ["view_file"]))
    fake = FakeOps([p], [step("scripts/file_ops_cmd.py", 'write x.txt --text "x"'), step("scripts/cat_cmd.py", "configs/missing.yaml"),
                         say("❌ 沒有完成：找不到 configs/missing.yaml"),
                         step("scripts/cat_cmd.py", "configs/missing.yaml"), say("❌ 沒有完成：還是找不到")])
    ollama.chat = fake
    out = agent.ops_plan("讀 configs/missing.yaml")       # 都只查詢：ops_plan 直接執行（不用確認）
    assert out.startswith("（計畫都只查詢、不會改變任何狀態，所以直接執行了）"), out[:80]
    rep = out.split("\n", 1)[1]
    assert "這一步不能用 file_ops" in fake.worker_msgs[1][-1]["content"], "計畫沒列的會改變狀態的技能：不能用"
    assert not os.path.exists(os.path.join(home, "x.txt"))
    assert rep.startswith("[ERROR] 計畫沒有做完：第 1 步沒有完成") and "還是找不到" in rep, rep


def t_ops_step_cap_wrapup(agent, ollama, tmp, home):
    """worker 用完步數：最後請它總結；做完了（而且真的用過技能）就算完成、交給檢查，沒做完才算失敗。"""
    from agent_core.config import OPS_WORKER_MAX_STEPS
    p = plan(item("看設定", "看 configs/nav.yaml", ["view_file"]), item("看目錄", "看 configs", ["list_dir"]))
    acts = [("scripts/cat_cmd.py", "configs/nav.yaml"), ("scripts/ls_cmd.py", "configs"), ("scripts/ls_cmd.py", "."),
            ("scripts/cat_cmd.py", "./configs/nav.yaml"), ("scripts/ls_cmd.py", "./configs")]
    busy = [step(*acts[k % len(acts)]) for k in range(OPS_WORKER_MAX_STEPS)]   # 每個動作最多兩次（第三次會被當成卡住）
    fake = FakeOps([p], busy + [step("scripts/ls_cmd.py", "configs"), say("一個檔案")])
    fake.wrapups = [{"done": True, "summary": "max_vel_x 是 0.26"}]
    ollama.chat = fake
    assert agent.ops_plan("看設定再看目錄", run_readonly=False).startswith("[PASS] 計畫（2 步）")
    assert agent.guard_check(OPS_RUN) is None, "都只查詢的計畫：執行時不用確認"
    rep = agent.run_tool(OPS_RUN)
    assert rep.startswith("[PASS] 計畫執行完成（2/2 步") and "max_vel_x 是 0.26" in rep, rep
    assert agent.ops_last["items"][0]["steps"] == OPS_WORKER_MAX_STEPS + 1, agent.ops_last["items"][0]["steps"]


def t_ops_plan_errors(agent, ollama, tmp, home):
    fake = FakeOps([plan(), plan()], [])
    ollama.chat = fake
    assert agent.ops_plan("ab").startswith("[ERROR] ops_plan 需要任務描述")
    out = agent.ops_plan("規劃一個做不到的任務")
    assert out.startswith("[ERROR] 規劃 session 沒有給出可以執行的步驟") and agent.ops_draft is None, out
    many = plan(*[item(f"第{i}步", f"查 {i}", ["list_dir"]) for i in range(8)])
    fake = FakeOps([many, many], [])
    ollama.chat = fake
    out = agent.ops_plan("拆很多步的任務", run_readonly=False)
    assert out.startswith("[PASS] 計畫（6 步）") and fake.plan_calls == 2, (out[:80], fake.plan_calls)
    agent.reset_conversation()
    assert agent.ops_draft is None, "/clear 時清掉計畫草稿"


# ---------------------------------------------------------------- 新技能
def t_file_ops(agent, ollama, tmp, home):
    script = os.path.join(agent.script_dir, "skills_system", "scripts", "file_ops_cmd.py")

    def run(raw):
        import shlex
        r = subprocess.run([sys.executable, script] + shlex.split(raw), cwd=home, capture_output=True, text=True,
                           env=dict(os.environ, HARNESS_RAW_ARGS=raw), timeout=60)
        return (r.stdout + r.stderr).strip()

    assert run("mkdir notes/2026").startswith("[PASS] 已建立目錄")
    assert run("mkdir notes/2026").startswith("[PASS] 目錄已經存在")
    out = run('write notes/2026/a.md --text "第一行\\n含 \\"引號\\" 的第二行"')
    assert out.startswith("[PASS] 已建立 notes/2026/a.md（2 行）"), out
    assert read(os.path.join(home, "notes/2026/a.md")) == '第一行\n含 "引號" 的第二行\n'
    assert run('append notes/2026/a.md --text "第三行"').startswith("[PASS] 已附加")
    assert read(os.path.join(home, "notes/2026/a.md")).endswith("第二行\n第三行\n")
    out = run('replace configs/nav.yaml --old "max_vel_x: 0.3" --new "max_vel_x: 0.5"')
    assert out.startswith("[ERROR]") and "出現 0 次" in out and "max_vel_x: 0.26" in out, "找不到原文：列出相關的行"
    out = run('replace configs/nav.yaml --old "max_vel_x: 0.26" --new "max_vel_x: 0.5"')
    assert out.startswith("[PASS] 已修改 configs/nav.yaml 第 2 行附近") and "備份在" in out, out
    bk = out.rsplit("備份在 ", 1)[1].strip()
    assert os.path.exists(bk) and "0.26" in read(bk) and bk.startswith(os.path.join(agent.script_dir, "logs", "file_backups"))
    out = run('replace configs/nav.yaml --old "_vel_x" --new "_v"')
    assert out.startswith("[ERROR]") and "出現 2 次" in out, out
    assert run("copy notes/2026/a.md notes/b.md").startswith("[PASS] 已複製")
    assert run("copy notes/2026/a.md notes/b.md").startswith("[ERROR] 目的已經存在")
    assert run("move notes/b.md notes/2026").startswith("[PASS] 已移動")
    assert os.path.exists(os.path.join(home, "notes/2026/b.md")) and not os.path.exists(os.path.join(home, "notes/b.md"))
    assert run('write /etc/agent_test.txt --text "x"').startswith("[ERROR] 不能在系統目錄操作")
    assert run("delete notes/b.md").startswith("[ERROR] 第一個參數要是動作"), "不提供刪除"


def t_guard_new_skills(agent, ollama, tmp, home):
    def info(cmd, args):
        return agent.state_change_info({"action": {"command": cmd, "args": args}})

    for cmd, args in [("scripts/docker_ctl_cmd.py", "status nav2"), ("scripts/docker_ctl_cmd.py", "logs nav2 --tail 20"),
                      ("scripts/docker_ctl_cmd.py", "env nav2 --grep ROS"), ("scripts/ROS2_param_cmd.py", "get /controller max_vel_x"),
                      ("scripts/ROS2_param_cmd.py", "list /controller"), ("scripts/rmf_handshake_cmd.py", "status tb1"),
                      ("scripts/host_runcmd_cmd.py", '"ls -la"'), ("scripts/ops_plan_cmd.py", '"重啟 nav2"')]:
        assert info(cmd, args) is None, f"唯讀的用法不用確認：{cmd} {args}"
    for cmd, args, skill in [("scripts/docker_ctl_cmd.py", "restart nav2", "docker_ctl"), ("scripts/docker_ctl_cmd.py", "stop nav2", "docker_ctl"),
                             ("scripts/ROS2_param_cmd.py", "set /controller max_vel_x 0.5", "ROS2_param"),
                             ("scripts/rmf_handshake_cmd.py", "yes tb1", "rmf_handshake"), ("scripts/rmf_handshake_cmd.py", "fin tb1", "rmf_handshake"),
                             ("scripts/ROS2_topic_pub_cmd.py", '/cmd_vel geometry_msgs/msg/Twist "{}"', "ROS2_topic_pub"),
                             ("scripts/file_ops_cmd.py", "mkdir x", "file_ops"), ("scripts/host_runcmd_cmd.py", '"touch x"', "host_runcmd")]:
        got = info(cmd, args)
        assert got and got["skill"] == skill, f"會改變狀態要確認：{cmd} {args} → {got}"


# ---------------------------------------------------------------- 寫測試
def main():
    results = []
    for name, fn in [("🧭 ops：規劃的程式檢查與修正、確認關卡是整份計畫、沒確認不執行、每一步一個 worker、檢查、報告與存檔", t_ops_plan_and_run),
                     ("🧭 ops：ops_run 帶任務一個動作完成（確認關卡先規劃、同任務不重規劃、規劃失敗不重試、/guard off、一步的任務交回主對話）", t_ops_run_one_action),
                     ("🧭 ops：沒核准的狀態變更 [DENIED]、沒用技能就說做完推回去、檢查沒過重試一次後標成「檢查沒過」繼續", t_ops_denied_retry_stop),
                     ("🧭 ops：計畫沒列的技能不能用、worker 回報做不到（❌）", t_ops_worker_failure_and_scope),
                     ("🧭 ops：worker 用完步數時請它總結：做完了就算完成（交給檢查）", t_ops_step_cap_wrapup),
                     ("🧭 ops：任務太短、規劃不出步驟、步驟太多（最多 6 步）、/clear 清掉草稿", t_ops_plan_errors),
                     ("file_ops：建目錄、含引號的內容、附加、取代要剛好一次、複製不覆蓋、移動、備份、系統目錄、不提供刪除", t_file_ops),
                     ("新技能的確認關卡：唯讀的用法不用問、會改變狀態的要問", t_guard_new_skills)]:
        scenario(name, fn, results)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
