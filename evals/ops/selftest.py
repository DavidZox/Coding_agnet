"""維運技能的離線自我測試：不需要 Ollama、不需要 docker。任務引擎（task_run、Plan 模式）的測試在 evals/task/selftest.py。

    python3 evals/ops/selftest.py

- file_ops（建目錄、寫入含引號的內容、附加、取代要剛好一次、複製不覆蓋——目的已經一模一樣算成功、移動、備份、系統目錄不能寫、不提供刪除）；
- 確認關卡：docker_ctl／ROS2_param／rmf_handshake 的唯讀用法不用問、會改變狀態的要問；task_run 的取消不用問。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts"]


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
    out = run("copy notes/2026/a.md notes/b.md")
    assert out.startswith("[PASS] 沒有再複製：notes/b.md 已經存在，內容跟 notes/2026/a.md 一模一樣"), "重試時已經複製好了：不算失敗"
    assert run('append notes/b.md --text "x"').startswith("[PASS]")
    assert run("copy notes/2026/a.md notes/b.md").startswith("[ERROR] 目的已經存在"), "內容不一樣：不覆蓋"
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
                      ("scripts/host_runcmd_cmd.py", '"ls -la"'), ("scripts/task_run_cmd.py", "--cancel")]:
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
    for name, fn in [("file_ops：建目錄、含引號的內容、附加、取代要剛好一次、複製不覆蓋、移動、備份、系統目錄、不提供刪除", t_file_ops),
                     ("新技能的確認關卡：唯讀的用法不用問、會改變狀態的要問", t_guard_new_skills)]:
        scenario(name, fn, results)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
