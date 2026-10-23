"""非編碼評測的沙盒：獨立的 Docker daemon（Docker-in-Docker）＋情境要用的容器＋檔案沙盒，以及讀回最後的狀態。

agent 的 docker 技能透過 DOCKER_HOST 只看得到這個 daemon，碰不到主機上真的容器（例如 amr-base-dev）；ROS 2 容器用
另外的 ROS_DOMAIN_ID、只在本機探索，跟正式的機器人網路隔離。

    python3 sandbox.py up            # 起 daemon、拉映像、建 rmf_sim 映像
    python3 sandbox.py reset <情境>   # 依情境重建容器與檔案（評測程式每個情境都會呼叫）
    python3 sandbox.py state         # 印出目前的狀態（容器、調度系統）
    python3 sandbox.py down          # 停掉 daemon（映像留在 volume 裡）
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# 評測用 cah_ops_dind（port 23750）；開發時可以用環境變數換成另一個 daemon（例如 cah_dev_dind／23751），不打擾正在跑的評測
DIND = os.environ.get("OPS_SANDBOX_DIND", "cah_ops_dind")
DIND_PORT = int(os.environ.get("OPS_SANDBOX_PORT", "23750"))
DOCKER_HOST = f"tcp://127.0.0.1:{DIND_PORT}"
SIM_IMAGE = "cahtest/rmf_sim:jazzy"
WEB_PORT, TRIGGER_PORT = 28020, 28002
IMAGES = ["ros:jazzy-ros-base", "ubuntu:24.04"]


def host_docker(*args, timeout=120):
    env = {k: v for k, v in os.environ.items() if k != "DOCKER_HOST"}
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, env=env)


def sd(*args, timeout=180, check=False, input=None):
    """在沙盒 daemon 執行 docker 指令。"""
    env = dict(os.environ, DOCKER_HOST=DOCKER_HOST)
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, env=env, input=input)
    if check and r.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)}：{r.stderr.strip()[-800:]}")
    return r


def dind_ip():
    r = host_docker("inspect", DIND, "--format", "{{json .NetworkSettings.Networks}}")
    nets = json.loads(r.stdout or "{}")
    return next((v.get("IPAddress") for v in nets.values() if v.get("IPAddress")), "127.0.0.1")


def urls():
    ip = dind_ip()
    return {"web_console": f"http://{ip}:{WEB_PORT}", "manual_trigger": f"http://{ip}:{TRIGGER_PORT}", "docker_host": DOCKER_HOST}


def up():
    r = host_docker("inspect", DIND, "--format", "{{.State.Running}}")
    if r.returncode != 0:
        host_docker("run", "-d", "--privileged", "--name", DIND, "-e", "DOCKER_TLS_CERTDIR=", "-p", f"127.0.0.1:{DIND_PORT}:2375",
                    "-v", f"{DIND}_data:/var/lib/docker", "docker:27-dind")
    elif r.stdout.strip() != "true":
        host_docker("start", DIND)
    for _ in range(60):
        if sd("info").returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("沙盒 daemon 沒有起來")
    have = set(sd("images", "--format", "{{.Repository}}:{{.Tag}}").stdout.split())
    for img in IMAGES:
        if img not in have:
            sd("pull", img, timeout=1800, check=True)
    sim_dir = os.path.join(HERE, "rmf_sim")
    digest = hashlib.sha1()   # 整個 rmf_sim/（含 fih_rmf_msgs/ 子目錄）：只改 msg 也要重建映像
    for root, dirs, files in os.walk(sim_dir):
        dirs.sort()
        for fn in sorted(files):
            p = os.path.join(root, fn)
            with open(p, "rb") as f:
                digest.update(os.path.relpath(p, sim_dir).encode() + f.read())
    want = digest.hexdigest()[:12]
    got = sd("image", "inspect", SIM_IMAGE, "--format", "{{index .Config.Labels \"src\"}}").stdout.strip()
    if got != want:
        sd("build", "-q", "--label", f"src={want}", "-t", SIM_IMAGE, sim_dir, timeout=1800, check=True)
    return urls()


def down():
    host_docker("stop", DIND)


# ================================================================ 容器
def _ubuntu(name, script, env=None, labels=None):
    args = ["create", "--name", name, "--label", "cahtest=1"]
    for k, v in (env or {}).items():
        args += ["-e", f"{k}={v}"]
    for k, v in (labels or {}).items():
        args += ["--label", f"{k}={v}"]
    return args + ["ubuntu:24.04", "bash", "-c", script]


LOG_WRITER = ("i=0; while true; do echo \"$(date +%H:%M:%S) INFO heartbeat seq=$i\"; "
              "if [ $((i % 6)) -eq 4 ]; then echo \"$(date +%H:%M:%S) ERROR E1203 lidar timeout on /scan (seq=$i)\"; fi; "
              "i=$((i+1)); sleep 1; done")
NAV2_FAIL = ("echo '[nav2_bringup] loading params /config/nav2_params.yaml'; sleep 1; "
             "echo '[map_server] ERROR: map file /maps/site_b.yaml not found'; echo '[nav2_bringup] shutting down'; exit 1")
CONTAINERS = {
    "web_cache": lambda: _ubuntu("web_cache", "mkdir -p /srv/cache && printf 'max_size=512M\\nport=8080\\nowner=ops\\n' > /etc/web_cache.conf "
                                              "&& exec sleep infinity", env={"CACHE_TTL": "300"}),
    "log_writer": lambda: _ubuntu("log_writer", LOG_WRITER),
    "nav2_test": lambda: _ubuntu("nav2_test", NAV2_FAIL, env={"ROS_DOMAIN_ID": "42"}),
    "db_backup": lambda: _ubuntu("db_backup", "echo 'backup started'; sleep 1; echo 'backup finished: 128 rows'; exit 0"),
    "scratch_tools": lambda: _ubuntu("scratch_tools", "exec sleep infinity"),
}
STOP_AFTER_START = {"nav2_test", "db_backup"}          # 啟動後自己會結束（停在 Exited）


def _sim_container(name, config, domain=None, publish=True, extra_cmd=None):
    args = ["create", "--name", name, "--label", "cahtest=1"]
    if publish:
        args += ["-p", f"{WEB_PORT}:8020", "-p", f"{TRIGGER_PORT}:8002"]
    if domain is not None:
        args += ["-e", f"ROS_DOMAIN_ID={domain}"]
    args.append(SIM_IMAGE)
    if extra_cmd:
        args += ["bash", "-c", extra_cmd]
    return args


def reset(world):
    """world：{"containers": [...], "sim": {rmf_sim 的設定} 或 None, "extra": [自訂的 create 參數], "stopped": [...], "wait": 秒}"""
    ids = sd("ps", "-aq").stdout.split()
    if ids:
        sd("rm", "-f", *ids, timeout=120)
    # 情境裡 agent 拉下來的映像（例如 docker run ubuntu 拉了 ubuntu:latest）也清掉，每個情境開始時的映像都一樣
    keep = set(IMAGES) | {SIM_IMAGE}
    extra = [n for n in sd("images", "--format", "{{.Repository}}:{{.Tag}}").stdout.split() if n not in keep and not n.endswith(":<none>")]
    if extra:
        sd("rmi", "-f", *extra, timeout=120)
    sim_cfg = world.get("sim")
    created = []
    if sim_cfg is not None:
        sd(*_sim_container("rmf_sim", sim_cfg), check=True)
        import tempfile
        fd, cfg_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(sim_cfg, f, ensure_ascii=False)
        sd("cp", cfg_path, "rmf_sim:/opt/rmf_sim/config.json", check=True)
        os.remove(cfg_path)
        created.append("rmf_sim")
    for name in world.get("containers", []):
        sd(*CONTAINERS[name](), check=True)
        created.append(name)
    for spec in world.get("extra", []):
        sd(*spec["create"], check=True)
        created.append(spec["name"])
    for name in created:
        sd("start", name, check=True)
    for name in world.get("stopped", []):
        sd("stop", "-t", "1", name)
    if sim_cfg is not None:
        _wait_http(urls()["web_console"] + "/api/robots", 30)
    time.sleep(float(world.get("wait", 2)))
    for name in STOP_AFTER_START & set(created):     # 確定已經自己結束
        for _ in range(20):
            if sd("inspect", name, "--format", "{{.State.Running}}").stdout.strip() == "false":
                break
            time.sleep(0.5)
    return created


def _wait_http(url, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{url} 沒有回應")


# ================================================================ 狀態
def containers_state():
    out = {}
    ids = sd("ps", "-aq").stdout.split()
    if not ids:
        return out
    r = sd("inspect", *ids)
    for c in json.loads(r.stdout or "[]"):
        st = c.get("State", {})
        out[c["Name"].lstrip("/")] = {"running": st.get("Running"), "status": st.get("Status"), "exit_code": st.get("ExitCode"),
                                       "started_at": st.get("StartedAt"), "restart_count": c.get("RestartCount"),
                                       "image": c.get("Config", {}).get("Image"), "labels": c.get("Config", {}).get("Labels") or {}}
    return out


def sim_state():
    try:
        with urllib.request.urlopen(urls()["web_console"] + "/api/sim_state", timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except OSError:
        return None


def fs_snapshot(root):
    snap = {}
    for dp, dns, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            try:
                with open(p, "rb") as f:
                    data = f.read()
                snap[rel] = {"sha1": hashlib.sha1(data).hexdigest(), "size": len(data), "mtime": os.path.getmtime(p),
                             "text": data.decode("utf-8", errors="replace") if len(data) <= 200_000 else None}
            except OSError:
                pass
        for d in dns:
            snap.setdefault(os.path.relpath(os.path.join(dp, d), root) + "/", {"dir": True})
    return snap


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "up"
    if cmd == "up":
        print(json.dumps(up(), ensure_ascii=False))
    elif cmd == "down":
        down()
    elif cmd == "state":
        print(json.dumps({"containers": containers_state(), "sim": (sim_state() or {}).get("distribute")}, ensure_ascii=False, indent=1))
    elif cmd == "reset":
        sys.path.insert(0, os.path.dirname(HERE))
        import scenarios
        sc = scenarios.BY_ID[sys.argv[2]]
        print(reset(sc["world"]))


if __name__ == "__main__":
    main()
