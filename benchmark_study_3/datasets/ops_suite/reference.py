"""每個非編碼情境的參考解法（直接操作沙盒，不經過模型），用來驗證情境「做得到」、檢查沒有寫錯：每一個都要拿滿分。

    python3 reference.py [--only id,...]

參考解法只用 agent 也拿得到的資訊（檔案沙盒、沙盒 daemon、rmf_sim 的 HTTP 與 ROS 2 介面），回覆裡寫出該有的事實。
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "sandbox"))
import checks      # noqa: E402
import fs_world    # noqa: E402
import sandbox     # noqa: E402
import scenarios   # noqa: E402
import scenarios_holdout as holdout   # noqa: E402

F = fs_world.facts()


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode() or "null")


def sim_state(urls):
    return http("GET", urls["web_console"] + "/api/sim_state")


def wait_pkg(urls, pid, status="COMPLETED", seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        p = sim_state(urls)["packages"].get(pid)
        if p and p["status"] == status:
            return True
        time.sleep(1)
    return False


def send(urls, pid, robot, stops):
    return http("POST", urls["web_console"] + "/api/send_tasks", [{"task_id": pid, "task_type": "regular", "level": "normal", "weight": 0,
                "assign_amr": robot, "loop": False, "loop_count": None, "stops": [{"station": s, "description": ""} for s in stops]}])


def ros(cmd, container="rmf_sim", domain=None):
    env = f"export ROS_DOMAIN_ID={domain}; " if domain is not None else ""
    r = sandbox.sd("exec", container, "bash", "-c", f"source /opt/ros/jazzy/setup.bash && source /workspaces/amr_base/install/setup.bash "
                   f"2>/dev/null; {env}{cmd}", timeout=60)
    return r.stdout + r.stderr


def current_item(urls, pid):
    return sim_state(urls)["packages"][pid]["current_item"]["item_id"]


def fin(urls, robot, item):
    return http("POST", urls["manual_trigger"] + "/batch_task_exec_fin", [{"robot_name": robot, "task_id": item}])


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


# ================================================================ 參考解法：回傳回覆文字
def solve(sid, root, urls):
    bm = F["battery_min"]
    if sid == "fs_newest_log":
        return f"最新的是 {F['newest_log']}，E1203 出現 {F['newest_e1203_count']} 次，最後一次在 {F['newest_e1203_last_time']}。"
    if sid == "fs_find_value":
        return "tb3 的 max_speed 是 0.55，設定在 configs/robots.yaml。"
    if sid == "fs_count_all":
        return f"E1203 總共 {F['e1203_total']} 次，最多的是 {F['e1203_max_file']}（robot_tb3.log）。"
    if sid == "fs_cd_relative":
        return "max_vel_x 是 0.5。"
    if sid == "fs_compare_backup":
        return "max_vel_x：0.5 對 0.35；controller_frequency：20.0 對 10.0。"
    if sid == "fs_edit_param":
        p = "configs/nav/nav_params.yaml"
        write(root, p, read(root, p).replace("max_vel_x: 0.5", "max_vel_x: 0.3"))
        return "已改成 0.3。"
    if sid == "fs_battery_report":
        rows = "\n".join(f"| {r} | {bm[r][0]} | {bm[r][1]} |" for r in sorted(bm))
        write(root, "reports/battery_min.md", "| 機器人 | 最低電量 | 時間 |\n|---|---|---|\n" + rows + "\n")
        return "已寫好 reports/battery_min.md。"
    if sid == "fs_archive_logs":
        shutil.move(os.path.join(root, "logs/2026-09-28"), os.path.join(root, "logs/archive/2026-09-28"))
        return "已移動 logs/2026-09-28。"
    if sid == "fs_copy_template":
        shutil.copytree(os.path.join(root, "templates/mission_template"), os.path.join(root, "missions/patrol_b"))
        for fn in ("mission.yaml", "README.md"):
            rel = f"missions/patrol_b/{fn}"
            write(root, rel, read(root, rel).replace("MISSION_NAME", "patrol_b"))
        return "已建立 missions/patrol_b。"
    if sid == "fs_typo_path":
        return "configs/robots.yaml 裡 tb2：max_speed 0.7、battery_low 20、home a0。"
    if sid == "fs_csv_max_temp":
        t = F["temp_max"]
        return f"最高 {t[0]}，{t[1]}，{t[2]}。"
    if sid == "fs_doc_question":
        return "不可以。轉 IDLE 時發 no 會蓋掉 yes，造成無限重送（R2）。"
    if sid == "dk_overview":
        return "web_cache、log_writer、scratch_tools 在跑；nav2_test Exited (1)、db_backup Exited (0)。"
    if sid == "dk_restart_backup":
        sandbox.sd("start", "db_backup", check=True)
        time.sleep(3)
        logs = sandbox.sd("logs", "db_backup").stdout
        return "重新啟動了 db_backup：" + logs.strip().splitlines()[-1]
    if sid == "dk_logs_error":
        logs = sandbox.sd("logs", "--tail", "50", "log_writer").stdout
        last = [ln for ln in logs.splitlines() if "ERROR" in ln][-1]
        return f"有，最後一筆：{last}"
    if sid == "dk_exec_conf":
        return sandbox.sd("exec", "web_cache", "cat", "/etc/web_cache.conf").stdout
    if sid == "dk_env_var":
        return "CACHE_TTL=" + sandbox.sd("exec", "web_cache", "printenv", "CACHE_TTL").stdout.strip()
    if sid == "dk_diagnose_exit":
        return "原因：" + sandbox.sd("logs", "nav2_test").stdout
    if sid == "dk_create_box":
        sandbox.sd("run", "-d", "--name", "scratch_box", "ubuntu:24.04", "sleep", "infinity", check=True)
        return "已建立 scratch_box，狀態 Up。"
    if sid == "dk_image_size":
        out = sandbox.sd("images", "ros:jazzy-ros-base", "--format", "{{.Repository}}:{{.Tag}} {{.Size}}").stdout
        return f"有：{out}"
    if sid == "dk_ambiguous":
        return "nav2_test 目前是 Exited (1)，已經停了。"
    if sid == "dk_stop_tools":
        sandbox.sd("stop", "-t", "1", "scratch_tools", check=True)
        return "已停止 scratch_tools。"
    if sid == "ros_nodes":
        out = ros("ros2 node list")
        return f"共 {len(out.split())} 個：{out}"
    if sid == "ros_topics_tb2":
        return ros("ros2 topic list | grep tb2")
    if sid == "ros_battery_tb3":
        out = ros("ros2 topic echo --once /tb3/robot_state")
        return "電量：" + re.search(r"battery_level: ([\d.]+)", out).group(1)
    if sid == "ros_lowest_battery":
        return "tb3 電量最低（64.0），在 a8 附近。"
    if sid == "ros_node_subs":
        return ros("ros2 node info /resource_allocator")
    if sid == "ros_param":
        return ros("ros2 param get /resource_allocator authorize_timeout_sec")
    if sid == "ros_domain_mismatch":
        return "talker_box 的 ROS_DOMAIN_ID 是 7，rmf_sim 是 42，domain 不同所以看不到。"
    if sid == "ros_moving":
        return "有在移動，目標 a7。"
    if sid == "ros_pub_yes":
        ros("ros2 topic pub --once /tb2/handshake_states fih_rmf_msgs/msg/HandshakeState \"{is_authored: 'yes'}\"")
        time.sleep(2)
        return "已發 yes，distribute 已 confirm。"
    if sid == "ros_hz":
        return "大約 2 Hz（每 0.5 秒一次）。"
    if sid == "hs_send_track":
        send(urls, "WP_TRACK", "tb2", ["home", "a3", "a7"])
        return "完成" if wait_pkg(urls, "WP_TRACK") else "沒有完成"
    if sid == "hs_busy_diag":
        return "WP_C3 指派給 tb3，tb3 對授權一直回 no（拒絕），授權逾時進 OverPending 再回流。"
    if sid == "hs_silent_diag":
        return "tb4 對授權沒有回應（沒有 handshake_states），心跳正常，TaskAgent 可能沒在跑。"
    if sid == "hs_lost_fin_fix":
        fin(urls, "tb2", current_item(urls, "WP_L2"))
        wait_pkg(urls, "WP_L2")
        return "補發 task_exec_fin，WP_L2 已完成。"
    if sid == "hs_offline_diag":
        return "tb5 離線（OFFLINE，沒有 robot_state 心跳），任務在等機器人。"
    if sid == "hs_cancel_one":
        http("DELETE", urls["web_console"] + "/api/work_packages/WP_DROP")
        return "已取消 WP_DROP。"
    if sid == "hs_trigger_yes":
        http("POST", urls["manual_trigger"] + "/batch_handshake", [{"robot_name": "tb1", "is_authored": "yes"},
                                                                 {"robot_name": "tb3", "is_authored": "yes"}])
        return "已送出。"
    if sid == "hs_semantic":
        send(urls, "WP_SEM", "tb1", ["a7"])
        wait_pkg(urls, "WP_SEM")
        return "tb1 已到 a7。"
    if sid == "hs_ovp_delete":
        deadline = time.time() + 30
        while time.time() < deadline:
            ov = sim_state(urls)["distribute"]["overpending"]
            if ov:
                http("DELETE", urls["web_console"] + "/api/overpending_tasks/" + ov[0])
                break
            time.sleep(0.5)
        return "已刪除。"
    if sid == "hs_status":
        return "WP_A 完成（COMPLETED）；WP_B 循環中；WP_C3 卡在授權（tb3 回 no，OverPending）。"
    if sid == "cx_fin_and_note":
        item = current_item(urls, "WP_L2")
        fin(urls, "tb2", item)
        wait_pkg(urls, "WP_L2")
        write(root, "ops_notes/2026-10-10.md", f"WP_L2 卡在第一站：tb2 已到站但 task_exec_fin 遺失。補發 {item} 的完成訊號後完成。\n")
        return "已處理並記錄。"
    if sid == "cx_shift_report":
        st = sim_state(urls)
        lines = [f"- {n}: {v['status']}" for n, v in sandbox.containers_state().items()]
        lines += [f"- {rid}: 電量 {r['battery']}，在 {r['station']}" for rid, r in st["robots"].items()]
        lines += [f"- {pid}: {p['status']}" for pid, p in st["packages"].items()]
        write(root, "handover/2026-10-10.md", "# 交班 2026-10-10\n" + "\n".join(lines) + "\n")
        return "已寫好。"
    if sid == "cx_restart_verify":
        sandbox.sd("start", "web_cache", check=True)
        time.sleep(1)
        conf = sandbox.sd("exec", "web_cache", "cat", "/etc/web_cache.conf").stdout
        write(root, "ops_notes/web_cache.md", f"重新啟動 web_cache；設定 {conf.strip()}（max_size=512M）\n")
        return "完成。"
    if sid == "cx_reassign":
        http("DELETE", urls["web_console"] + "/api/work_packages/WP_C3")
        send(urls, "WP_C3_TB1", "tb1", ["a6"])
        wait_pkg(urls, "WP_C3_TB1")
        return "已改派 tb1 並完成。"
    if sid == "cx_batch_dispatch":
        for pid, robot, stops in (("WP_M01", "tb1", ["home", "a3"]), ("WP_M02", "tb2", ["a0", "a7"]), ("WP_M03", "tb3", ["a8", "a6"])):
            send(urls, pid, robot, stops)
        time.sleep(8)
        return "WP_M01、WP_M02 授權成功；WP_M03 失敗：tb3 回 no，進 OverPending。"
    if sid == "cx_config_dispatch":
        p = "configs/robots.yaml"
        text = read(root, p)
        text = text.replace("  - id: tb2\n    model: tinyRobot\n    max_speed: 0.7", "  - id: tb2\n    model: tinyRobot\n    max_speed: 0.6")
        write(root, p, text)
        send(urls, "WP_SPEED", "tb2", ["home", "a3"])
        wait_pkg(urls, "WP_SPEED")
        return "完成。"
    if sid == "cx_domain_fix":
        out = ros("ros2 topic echo --once /chatter", domain=7)
        return f"ROS_DOMAIN_ID 不同（talker_box 7、rmf_sim 42）；用 ROS_DOMAIN_ID=7 收到：{out}"
    if sid == "cx_incident_timeline":
        log = read(root, "logs/2026-10-10/robot_tb3.log")
        errs = [ln for ln in log.splitlines() if "ERROR" in ln]
        write(root, "reports/tb3_timeline.md", "# tb3 2026-10-10\n" + "\n".join(errs) + "\n- 調度：tb3 對授權回 no\n")
        return "已寫好。"
    if sid.startswith("ho_"):
        return solve_holdout(sid, root, urls)
    raise KeyError(sid)


def solve_holdout(sid, root, urls):
    H = holdout
    if sid == "ho_fs_e2001_files":
        return "；".join(f"{rel}：{n} 次" for rel, n in sorted(H.E2001.items()))
    if sid == "ho_fs_backup_edit":
        p = "configs/robots.yaml"
        text = read(root, p)
        write(root, p + ".bak", text)
        write(root, p, text.replace("  - id: tb4\n    model: deliveryBot\n    max_speed: 1.0\n    battery_low: 15",
                                    "  - id: tb4\n    model: deliveryBot\n    max_speed: 1.0\n    battery_low: 18"))
        return "已備份成 configs/robots.yaml.bak，tb4 的 battery_low 改成 18。"
    if sid == "ho_fs_csv_avg":
        return f"tb2 的平均電量約 {H.TB2_AVG_1}。"
    if sid == "ho_fs_handover_append":
        p = "handover/2026-10-09.md"
        text = read(root, p)
        write(root, p, text + ("" if text.endswith("\n") else "\n") + "- tb3 今天 E1203 共 5 次，已通知硬體組。\n")
        return "已加上。"
    if sid == "ho_dk_conf_fields":
        return sandbox.sd("exec", "web_cache", "cat", "/etc/web_cache.conf").stdout
    if sid == "ho_dk_running_count":
        names = sandbox.sd("ps", "--format", "{{.Names}}").stdout.split()
        return f"共 {len(names)} 個：{'、'.join(sorted(names))}"
    if sid == "ho_dk_backup_rows":
        return sandbox.sd("logs", "db_backup").stdout
    if sid == "ho_dk_restart_nav":
        sandbox.sd("start", "nav2_test", check=True)
        time.sleep(4)
        return "起不來：" + sandbox.sd("logs", "--tail", "3", "nav2_test").stdout + sandbox.sd("logs", "--tail", "3", "nav2_test").stderr
    if sid == "ho_ros_tb2_state":
        out = ros("ros2 topic echo --once /tb2/robot_state")
        return f"tb2 在 a0，電量 {re.search(r'battery_level: ([0-9.]+)', out).group(1)}。"
    if sid == "ho_ros_param_vs_file":
        out = ros("ros2 param get /resource_allocator threshold_recovery_sec")
        return f"{out.strip()}；configs/rmf/fleet.yaml 寫的是 10，不一樣。"
    if sid == "ho_ros_param_list":
        return ros("ros2 param list /resource_allocator")
    if sid == "ho_ros_agent_sub":
        return ros("ros2 node info /tb3_task_agent")
    if sid == "ho_hs_send_tb3":
        send(urls, "WP_HO3", "tb3", ["a8", "a6"])
        return "完成" if wait_pkg(urls, "WP_HO3") else "沒有完成"
    if sid == "ho_hs_silent_tb2":
        return "WP_X2 指派給 tb2，tb2 對授權沒有回應（沒有 handshake_states），不是拒絕。"
    if sid == "ho_hs_cancel_loop":
        http("DELETE", urls["web_console"] + "/api/work_packages/WP_LOOP1")
        return "已取消 WP_LOOP1，WP_KEEP2 沒動。"
    if sid == "ho_hs_fin_tb1":
        fin(urls, "tb1", current_item(urls, "WP_F1"))
        wait_pkg(urls, "WP_F1")
        return "補發 task_exec_fin，WP_F1 已完成。"
    if sid == "ho_cx_cache_cycle":
        sandbox.sd("stop", "-t", "1", "web_cache", check=True)
        sandbox.sd("start", "web_cache", check=True)
        ttl = sandbox.sd("exec", "web_cache", "printenv", "CACHE_TTL").stdout.strip()
        write(root, "ops_notes/cache.md", f"- {time.strftime('%Y-%m-%d %H:%M')} 重新啟動 web_cache，CACHE_TTL={ttl}\n")
        return f"完成，CACHE_TTL={ttl}。"
    if sid == "ho_cx_diag_report":
        write(root, "reports/WP_D4.md", "# WP_D4\n- 機器人：tb4\n- 卡在授權（authorize）階段：tb4 沒有回應 handshake\n- 建議：請機器人端確認 TaskAgent\n")
        return "已寫好 reports/WP_D4.md。"
    if sid == "ho_cx_backup_edit_dispatch":
        p = "configs/robots.yaml"
        text = read(root, p)
        write(root, p + ".bak", text)
        write(root, p, text.replace("  - id: tb1\n    model: tinyRobot\n    max_speed: 0.8", "  - id: tb1\n    model: tinyRobot\n    max_speed: 0.9"))
        send(urls, "WP_HO_SPEED", "tb1", ["home", "a3"])
        wait_pkg(urls, "WP_HO_SPEED")
        return "已備份、改成 0.9，tb1 跑完了。"
    if sid == "ho_cx_e1203_by_day":
        rows = "\n".join(f"| {d} | {n} |" for d, n in sorted(H.E1203_BY_DAY.items()))
        write(root, "reports/e1203_by_day.md", "| 日期 | E1203 次數 |\n|---|---|\n" + rows + "\n")
        return f"最多的是 {H.E1203_MAX_DAY}，{H.E1203_BY_DAY[H.E1203_MAX_DAY]} 次。"
    raise KeyError(sid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--set", default="main", choices=["main", "holdout", "all"])
    ap.add_argument("--null", action="store_true", help="什麼都不做、只回一句不知道：每一個情境都應該不及格（檢查不是白送的）")
    args = ap.parse_args()
    urls = sandbox.up()
    ok_all = 0
    pool = {"main": scenarios.SCENARIOS, "holdout": holdout.HOLDOUT, "all": scenarios.SCENARIOS + holdout.HOLDOUT}[args.set]
    scs = [s for s in pool if not args.only or s["id"] in args.only.split(",")]
    for sc in scs:
        root = os.path.join(tempfile.mkdtemp(prefix="ops_ref_"), "ops_home")
        try:
            sandbox.reset(sc["world"])
            fs_world.build(root, sc.get("fs_extra"), urls)
            dk0, fs0 = sandbox.containers_state(), sandbox.fs_snapshot(root)
            sim0 = sandbox.sim_state() if sc["world"].get("sim") is not None else None
            reply = "我不知道，沒有做任何事。" if args.null else solve(sc["id"], root, urls)
            cwd = "configs/nav" if sc["id"] == "fs_cd_relative" and not args.null else ""
            ctx = {"replies": [reply], "tool_calls": [], "guards": 0, "cwd": cwd, "fs0": fs0, "fs1": sandbox.fs_snapshot(root),
                   "dk0": dk0, "dk1": sandbox.containers_state(), "sim1": sandbox.sim_state() if sim0 is not None else None,
                   "sim_t0": (sim0 or {}).get("t", 0)}
            res = checks.score(sc, ctx)
            good = (not res["passed"]) if args.null else res["passed"]
            ok_all += good
            bad = [k for k, v in res["checks"].items() if not v]
            print(("✅" if good else "❌"), sc["id"], ("" if good else f"沒過：{bad} 禁止：{res['forbidden']} 回覆：{reply[:300]}"),
                  flush=True)
        finally:
            shutil.rmtree(os.path.dirname(root), ignore_errors=True)
    print(f"{ok_all}/{len(scs)} 個" + ("情境在什麼都不做時不及格" if args.null else "參考解法拿滿分"))


if __name__ == "__main__":
    main()
