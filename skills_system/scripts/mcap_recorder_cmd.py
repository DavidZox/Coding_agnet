#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import subprocess
import argparse
from datetime import datetime

def get_available_topics():
    try:
        result = subprocess.run(['ros2', 'topic', 'list'], capture_output=True, text=True, check=True)
        topics = [t.strip() for t in result.stdout.splitlines() if t.strip()]
        return sorted(list(set(topics)))
    except Exception as e:
        print(f"[ERROR] 無法取得 ROS 2 Topic 列表: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="ROS 2 MCAP Experiment Recorder (Agent-Ready)")
    parser.add_argument("--topics", nargs='*', help="要錄製的 Topic 列表，例如 /cmd_vel /diagnostics")
    parser.add_argument("--all", action="store_true", help="錄製所有 Topic (-a)")
    parser.add_argument("--duration", type=int, default=0, help="定時錄製秒數 (0 表示手動停止)")
    parser.add_argument("--toolkit_dir", type=str, default="./toolkit", help="工具箱根目錄")
    args = parser.parse_args()

    # 決定工作目錄
    script_dir = os.path.dirname(os.path.abspath(__file__))
    toolkit_dir = os.path.abspath(args.toolkit_dir) if args.toolkit_dir != "./toolkit" else os.path.join(script_dir, "toolkit")
    exp_root = os.path.join(toolkit_dir, "experiment_logs")
    os.makedirs(exp_root, exist_ok=True)

    session_name = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    target_dir = os.path.join(exp_root, session_name)
    bag_dir = os.path.join(target_dir, "bag")
    os.makedirs(bag_dir, exist_ok=True)

    topics_to_record = []

    if args.all:
        topics_to_record = ["-a"]
    elif args.topics:
        topics_to_record = args.topics
        if "/rosout" not in topics_to_record:
            topics_to_record.append("/rosout")
        duration = args.duration
    else:
        # 互動式選單模式 (人類操作)
        print(f"\n========================================")
        print(f" ROS 2 實驗數據手動錄製工具")
        print(f"========================================")
        print("1) 預設核心 Topic 組合")
        print("2) 錄製全部現有 Topic (-a)")
        print("3) 動態檢索並選擇 Topic")
        choice = input("請選擇錄製模式 [1-3]: ").strip()

        if choice == "1":
            topics_to_record = [
                "/sensor_scan", "/cmd_vel", "/cmd_vel_raw",
                "/diagnostics", "/diagnostics_agg",
                "/system/safety_command", "/tf", "/tf_static", "/rosout"
            ]
        elif choice == "2":
            topics_to_record = ["-a"]
        elif choice == "3":
            all_topics = get_available_topics()
            if not all_topics:
                print("[ERROR] 找不到任何作用中的 Topic，請確認 ROS 2 節點已啟動。")
                sys.exit(1)
            print("\n可用 Topic 清單:")
            for idx, t in enumerate(all_topics, 1):
                print(f" [{idx}] {t}")
            sel = input("\n請輸入欲錄製的編號（以半形空白分隔，例如：1 3 5）: ").strip()
            selected_indices = [int(x) - 1 for x in sel.split() if x.isdigit()]
            topics_to_record = [all_topics[i] for i in selected_indices if 0 <= i < len(all_topics)]
            if "/rosout" not in topics_to_record:
                topics_to_record.append("/rosout")
        else:
            print("[ERROR] 無效的選擇。")
            sys.exit(1)

        dur_input = input("請輸入錄製秒數 (輸入 0 表示持續錄製直到按下 Ctrl+C): ").strip()
        duration = int(dur_input) if dur_input.isdigit() else 0

    print(f"\n[INFO] 實驗資料將錄製至: {bag_dir}")
    rosout_log_path = os.path.join(target_dir, "rosout.log")
    terminal_log_path = os.path.join(target_dir, "terminal.log")

    # 啟動 rosout 獨立日誌記錄
    rosout_proc = None
    formatter_script = os.path.join(script_dir, "rosout_formatter.py")
    try:
        if os.path.exists(formatter_script):
            rosout_cmd = f"ros2 topic echo /rosout 2>/dev/null | python3 -u {formatter_script}"
        else:
            rosout_cmd = "ros2 topic echo /rosout 2>/dev/null"
        
        with open(rosout_log_path, "w") as rosout_f:
            rosout_proc = subprocess.Popen(rosout_cmd, shell=True, stdout=rosout_f, stderr=subprocess.STDOUT)
    except Exception as e:
        print(f"[WARN] 無法啟動 rosout 獨立記錄: {e}")

    # 組裝 ros2 bag record 指令
    cmd = ["ros2", "bag", "record", "-s", "mcap", "-o", bag_dir] + topics_to_record
    print(f"[INFO] 執行錄製指令: {' '.join(cmd)}")

    bag_proc = None
    try:
        with open(terminal_log_path, "w") as term_f:
            bag_proc = subprocess.Popen(cmd, stdout=term_f, stderr=subprocess.STDOUT)
            
            if duration > 0:
                print(f"[INFO] 開始定時錄製 {duration} 秒...")
                for remaining in range(duration, 0, -1):
                    if bag_proc.poll() is not None:
                        break
                    sys.stdout.write(f"\r[錄製中] 剩餘時間: {remaining} 秒...")
                    sys.stdout.flush()
                    time.sleep(1)
                print("\n[INFO] 錄製時間到，正在安全停止並封裝...")
                bag_proc.terminate()
            else:
                print("[INFO] 正在錄製中... 按下 Ctrl+C 即可停止並儲存。")
                bag_proc.wait()
    except KeyboardInterrupt:
        print("\n[INFO] 收到手動中斷訊號 (Ctrl+C)，正在安全停止錄製...")
        if bag_proc:
            bag_proc.terminate()
    finally:
        if bag_proc:
            bag_proc.wait()
        if rosout_proc:
            rosout_proc.terminate()
            rosout_proc.wait()
        print(f"\n[OK] 錄製結束！實驗資料已完整封裝於: {target_dir}")

if __name__ == "__main__":
    main()