#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import yaml
from mcap.reader import make_reader
import rclpy.serialization
from rosidl_runtime_py.utilities import get_message

def inspect_mcap(slice_dir):
    mcap_path = os.path.join(slice_dir, "rosbag2.mcap")
    metadata_yaml_path = os.path.join(slice_dir, "metadata.yaml")

    if not os.path.exists(mcap_path):
        print(f"[ERROR] 找不到 mcap 檔案：{mcap_path}")
        return

    print(f"\n========================================")
    print(f" 正在分析切片檔案：{slice_dir}")
    print(f"========================================")

    # 1. 優先讀取 metadata.yaml 中的 ai_features 與 available_keys 供 AI / 使用者參考
    topic_keys_dict = {}
    if os.path.exists(metadata_yaml_path):
        try:
            with open(metadata_yaml_path, 'r', encoding='utf-8') as mf:
                meta_data = yaml.safe_load(mf)
                bag_info = meta_data.get('rosbag2_bagfile_information', {})
                print(f"\n[1] 區段統計摘要 (Duration: {bag_info.get('duration', {}).get('nanoseconds', 0) / 1e9}s, Total Msgs: {bag_info.get('message_count', 0)}):")
                
                for t_info in bag_info.get('topics_with_message_count', []):
                    t_meta = t_info.get('topic_metadata', {})
                    t_name = t_meta.get('name')
                    t_count = t_meta.get('message_count')
                    t_keys = t_meta.get('available_keys', [])
                    t_feat = t_meta.get('ai_features', {})
                    
                    topic_keys_dict[t_name] = t_keys
                    print(f"  - Topic: {t_name} (數量: {t_count}, 頻率: {t_feat.get('avg_frequency_hz', 0)}Hz)")
                    print(f"    預先萃取可用 Keys: {t_keys}")
        except Exception as e:
            print(f"  (讀取 metadata.yaml 失敗: {e})")

    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()

        # 2. 讀取檔案級 Metadata (AI 診斷註記)
        print("\n[2] 檔案級 Metadata (AI 診斷註記):")
        try:
            for metadata in reader.get_metadata():
                print(f"  - 名稱: {metadata.name}")
                print(f"    內容: {metadata.metadata}")
        except Exception as e:
            print(f"  (無額外 Metadata: {e})")

        if not summary or not summary.channels:
            print("[WARN] 此切片中沒有找到任何 Channels。")
            return

        channels_list = list(summary.channels.values())
        print(f"\n[3] 可用的 Topic 列表 (共 {len(channels_list)} 個):")
        for idx, ch in enumerate(channels_list, 1):
            schema = summary.schemas.get(ch.schema_id)
            msg_type = schema.name if schema else "unknown"
            print(f"  {idx}) Topic: {ch.topic} [Type: {msg_type}]")

        # 3. 互動選擇要調閱哪一個 Topic 與特定的 Key
        try:
            choice = input("\n請選擇想深入調閱的 Topic 編號 (輸入 0 離開): ").strip()
            if not choice.isdigit() or int(choice) == 0:
                return
            
            selected_idx = int(choice) - 1
            if selected_idx < 0 or selected_idx >= len(channels_list):
                print("[ERROR] 無效的編號。")
                return

            target_ch = channels_list[selected_idx]
            target_schema = summary.schemas.get(target_ch.schema_id)
            msg_type_str = target_schema.name if target_schema else None

            print(f"\n已選擇 Topic: {target_ch.topic} (型別: {msg_type_str})")

            # 取得該 topic 在 metadata 中預先記錄的 available_keys
            available_keys = topic_keys_dict.get(target_ch.topic, [])

            if not available_keys:
                print("[WARN] 此 Topic 沒有可用的 Keys 欄位（可能為原始二進位資料）。")
                return

            # 改為使用 1) 2) 3) 編號清單讓使用者挑選 Key
            print(f"\n[4] 該 Topic 可用的欄位 Keys (共 {len(available_keys)} 個):")
            for idx, k in enumerate(available_keys, 1):
                print(f"  {idx}) {k}")

            key_choice_input = input("\n請選擇想調閱的欄位 Key 編號 (輸入 0 離開): ").strip()
            if not key_choice_input.isdigit() or int(key_choice_input) == 0:
                return

            key_idx = int(key_choice_input) - 1
            if key_idx < 0 or key_idx >= len(available_keys):
                print("[ERROR] 無效的編號。")
                return

            key_choice = available_keys[key_idx]

            msg_class = get_message(msg_type_str) if msg_type_str else None
            if not msg_class:
                print("[ERROR] 無法載入該訊息型別類別。")
                return

            print(f"\n--- 正在擷取並展開欄位 [{key_choice}] 的時序數據 (前 15 筆) ---")
            count = 0
            for schema, channel, message in reader.iter_messages(topics=[target_ch.topic]):
                try:
                    ros_msg = rclpy.serialization.deserialize_message(message.data, msg_class)
                    val = getattr(ros_msg, key_choice)
                    print(f"  [時間戳: {message.log_time}] {key_choice} = {val}")
                    count += 1
                    if count >= 15:
                        print("  ... (為節省篇幅，僅顯示前 15 筆)")
                        break
                except Exception:
                    pass

        except Exception as ex:
            print(f"[ERROR] 解析過程中發生錯誤: {ex}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 mcap_analyzer.py <sliced_bag_directory>")
        sys.exit(1)
    
    slice_dir = sys.argv[1]
    inspect_mcap(slice_dir)

if __name__ == "__main__":
    main()