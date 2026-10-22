#!/usr/bin/env python3
"""隨機情境錄製產生器（主機端）：把模擬程式送進測試容器執行，產生一組 MCAP（rosbag2 格式）＋評分標準 cases.json。

    python3 evals/datagen/generate.py --set s2 --seed 2 --n 60            # → test_data/recordings/gen/s2/
    python3 evals/datagen/generate.py --set s2 --seed 2 --n 60 --only 3,7 # 只重產這幾份
    python3 evals/datagen/generate.py --set s3 --seed 3 --n 20 --require bridge   # 每一份都有 bridge
    python3 evals/datagen/check_facts.py test_data/recordings/gen/s2/cases.json   # 先驗程式那一層（不呼叫模型）
    python3 evals/analysis/regression.py --run --runs 2 --cases-file test_data/recordings/gen/s2/cases.json \\
        --data-root /workspace/experiment_logs/gen/s2 --container cah_analysis_test --model gemma4:26b --out evals/results/gen_s2

容器要有 ROS 2 Jazzy 與自訂訊息（diagnostics_package、base_motor_controller、fih_rmf_msgs，見 README.md），數據根目錄
test_data/recordings 掛載成容器的 /workspace/experiment_logs。同一個 seed 每次產生一樣的數據。"""
import argparse
import base64
import io
import os
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
FILES = ["sim_core.py", "sim_diag.py", "sim_base.py", "sim_nav.py", "sim_rmf.py", "sim_vslam.py", "sim_bridge.py", "sim_scenarios.py", "sim_main.py"]
COMMON = os.path.join(PROJECT, "skills_system", "scripts", "_ros2_data_common.py")   # 分析程式的定義（中斷、開始／停止發布的門檻）


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--set", required=True, help="這一組的名稱（資料夾 gen/<名稱>）")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--only", default="")
    p.add_argument("--require", default="", help="一定要有的子系統（逗號分隔：diagnostics、base、nav、rmf、vslam、bridge）")
    p.add_argument("--container", default="cah_analysis_test")
    p.add_argument("--host-root", default=os.path.join(PROJECT, "test_data", "recordings"))
    p.add_argument("--container-root", default="/workspace/experiment_logs")
    p.add_argument("--workspace", default="/workspace/ws", help="容器裡有自訂訊息的 Workspace")
    args = p.parse_args()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in FILES:
            tar.add(os.path.join(HERE, f), arcname=f)
        tar.add(COMMON, arcname="_ros2_data_common.py")
    out = f"{args.container_root.rstrip('/')}/gen/{args.set}"
    cmd = ("source /opt/ros/jazzy/setup.bash && source " + args.workspace + "/install/setup.bash && "
           'd=$(mktemp -d /tmp/datagen.XXXXXX) && base64 -d | tar -xz -C "$d" && '
           f'ROS2_TOOL_WORKER=1 PYTHONDONTWRITEBYTECODE=1 python3 "$d/sim_main.py" --seed {args.seed} --n {args.n} --out {out}'
           + (f" --only {args.only}" if args.only else "") + (f" --require {args.require}" if args.require else "")
           + '; rc=$?; rm -rf "$d"; exit $rc')
    r = subprocess.run(["docker", "exec", "-i", "-u", "ubuntu", args.container, "bash", "-lc", cmd],
                       input=base64.b64encode(buf.getvalue()).decode("ascii"), text=True)
    host = os.path.join(args.host_root, "gen", args.set)
    print(f"主機上的位置：{host}")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
