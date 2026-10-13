#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import yaml
import argparse
from datetime import datetime
from mcap.reader import make_reader
from mcap.writer import Writer
import rclpy.serialization
from rosidl_runtime_py.utilities import get_message

def parse_rosout_log(log_path):
    if not os.path.exists(log_path):
        return []
    events = []
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('[') and ']' in line:
                try:
                    level_end = line.index(']')
                    level = line[1:level_end]
                    rest = line[level_end+2:]
                    if rest.startswith('['):
                        ts_end = rest.index(']')
                        timestamp_str = rest[1:ts_end]
                        timestamp = float(timestamp_str)
                        events.append({
                            'level': level,
                            'timestamp': timestamp,
                            'timestamp_str': timestamp_str,
                            'raw': line
                        })
                except Exception:
                    continue
    return events

def main():
    parser = argparse.ArgumentParser(description="ROS 2 MCAP Smart Slicer (Agent-Ready)")
    parser.add_argument("experiment_dir", type=str, help="實驗資料夾路徑")
    parser.add_argument("bag_name", type=str, help="原始 bag 子資料夾名稱")
    parser.add_argument("--indices", nargs='*', type=int, help="要切片的事件編號清單 (1發起起算)")
    parser.add_argument("--pre", type=float, default=5.0, help="事件前緩衝秒數 (預設 5.0)")
    parser.add_argument("--post", type=float, default=5.0, help="事件後緩衝秒數 (預設 5.0)")
    args = parser.parse_args()
        
    exp_dir = args.experiment_dir
    bag_name = args.bag_name
    
    log_path = os.path.join(exp_dir, "rosout.log")
    bag_path = os.path.join(exp_dir, bag_name)
    
    if not os.path.exists(bag_path):
        print(f"[ERROR] 找不到 bag 資料夾：{bag_path}")
        sys.exit(1)

    mcap_files = [f for f in os.listdir(bag_path) if f.endswith('.mcap')]
    if not mcap_files:
        print(f"[ERROR] 在 {bag_path} 中找不到任何 .mcap 檔案")
        sys.exit(1)
    
    source_mcap_file = os.path.join(bag_path, mcap_files[0])
    events = parse_rosout_log(log_path)
    if not events:
        print("[WARN] rosout.log 中沒有解析到任何有效的事件記錄。")
        sys.exit(0)

    selected_indices = []
    pre_sec = args.pre
    post_sec = args.post

    if args.indices:
        # Agent 參數模式
        selected_indices = [i - 1 for i in args.indices if 0 <= i - 1 < len(events)]
    else:
        # 互動模式
        print(f"\n=== 步驟 1: 選擇日誌標記層級 (Log Level) ===")
        levels = sorted(list(set(e['level'] for e in events)))
        for idx, lvl in enumerate(levels, 1):
            count = sum(1 for e in events if e['level'] == lvl)
            print(f" {idx}) {lvl} (共 {count} 筆)")
        print(f" 0) 全部顯示")
        
        choice = input("請選擇要篩選的標級代號: ").strip()
        selected_level = None
        if choice != "0" and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(levels):
                selected_level = levels[idx]

        filtered_events = [e for e in events if selected_level is None or e['level'] == selected_level]
        
        print(f"\n=== 步驟 2: 選擇觸發的時間戳記事件 (支援多選) ===")
        print(f"{'No.':<4} | {'Level':<6} | {'Timestamp':<18} | {'Message Content'}")
        print("-" * 80)
        for idx, e in enumerate(filtered_events, 1):
            msg_preview = e['raw'].split(']: ', 1)[1] if ']: ' in e['raw'] else e['raw']
            if len(msg_preview) > 40:
                msg_preview = msg_preview[:37] + "..."
            print(f" {idx:<3} | {e['level']:<6} | {e['timestamp_str']:<18} | {msg_preview}")

        ev_choice = input("\n請選擇觸發異常/關注的事件編號（可輸入多個，以半形空白或逗號分隔）: ").strip()
        
        raw_indices = []
        for part in ev_choice.replace(',', ' ').split():
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(filtered_events):
                    if idx not in raw_indices:
                        raw_indices.append(idx)
        
        # 對應回全域 events
        for r_idx in raw_indices:
            target_ev = filtered_events[r_idx]
            global_idx = events.index(target_ev)
            selected_indices.append(global_idx)

        pre_input = input("請輸入基準時間「前」要擷取多少秒 (預設 5): ").strip()
        post_input = input("請輸入基準時間「後」要擷取多少秒 (預設 5): ").strip()
        pre_sec = float(pre_input) if pre_input.replace('.', '', 1).isdigit() else 5.0
        post_sec = float(post_input) if post_input.replace('.', '', 1).isdigit() else 5.0

    if not selected_indices:
        print("[ERROR] 沒有選擇任何有效的事件編號。")
        sys.exit(1)

    print(f"\n=== 正在進行高效切片與 AI Metadata 註記 ===")
    for i, event_idx in enumerate(selected_indices, 1):
        target_event = events[event_idx]
        target_time = target_event['timestamp']
        
        start_time_sec = max(0.0, target_time - pre_sec)
        end_time_sec = target_time + post_sec

        start_time_ns = int(start_time_sec * 1e9)
        end_time_ns = int(end_time_sec * 1e9)
        duration_sec = end_time_sec - start_time_sec

        output_bag_name = f"sliced_bag_{i}_{target_event['timestamp_str'].replace('.', '_')}"
        output_bag_dir = os.path.join(exp_dir, output_bag_name)
        os.makedirs(output_bag_dir, exist_ok=True)
        
        output_mcap_file = os.path.join(output_bag_dir, "rosbag2.mcap")

        schema_map = {}
        channel_map = {}
        topic_msg_counts = {}
        topic_keys_cache = {}
        total_messages = 0

        with open(source_mcap_file, "rb") as f_in, open(output_mcap_file, "wb") as f_out:
            reader = make_reader(f_in)
            writer = Writer(f_out)
            writer.start(profile="ros2")
            
            summary = reader.get_summary()
            if summary and summary.schemas:
                for schema in summary.schemas.values():
                    new_schema_id = writer.register_schema(name=schema.name, encoding=schema.encoding, data=schema.data)
                    schema_map[schema.id] = new_schema_id
            
            if summary and summary.channels:
                for channel in summary.channels.values():
                    new_schema_id = schema_map.get(channel.schema_id, 0)
                    new_channel_id = writer.register_channel(topic=channel.topic, message_encoding=channel.message_encoding, schema_id=new_schema_id, metadata=channel.metadata)
                    channel_map[channel.id] = new_channel_id
                    topic_msg_counts[channel.topic] = 0
            
            for schema, channel, message in reader.iter_messages():
                if start_time_ns <= message.log_time <= end_time_ns:
                    new_channel_id = channel_map.get(channel.id)
                    if new_channel_id is not None:
                        writer.add_message(channel_id=new_channel_id, log_time=message.log_time, data=message.data, publish_time=message.publish_time, sequence=message.sequence)
                        total_messages += 1
                        
                        for ch_id, mapped_id in channel_map.items():
                            if mapped_id == new_channel_id:
                                orig_ch = summary.channels[ch_id]
                                t_name = orig_ch.topic
                                topic_msg_counts[t_name] = topic_msg_counts.get(t_name, 0) + 1
                                
                                if t_name not in topic_keys_cache:
                                    sch = summary.schemas.get(orig_ch.schema_id)
                                    if sch and sch.name:
                                        try:
                                            msg_cls = get_message(sch.name)
                                            if msg_cls:
                                                ros_obj = rclpy.serialization.deserialize_message(message.data, msg_cls)
                                                if hasattr(ros_obj, '__slots__'):
                                                    topic_keys_cache[t_name] = list(ros_obj.__slots__)
                                        except Exception:
                                            pass
                                    if t_name not in topic_keys_cache:
                                        topic_keys_cache[t_name] = []

            writer.add_metadata(
                name="ai_slice_diagnostic_summary",
                data={
                    "trigger_timestamp": target_event['timestamp_str'],
                    "trigger_level": target_event['level'],
                    "trigger_message": target_event['raw'],
                    "window_duration_sec": str(duration_sec),
                    "total_messages": str(total_messages)
                }
            )
            writer.finish()

        metadata_path = os.path.join(output_bag_dir, "metadata.yaml")
        topics_info = []
        for topic_name, count in topic_msg_counts.items():
            if count > 0:
                freq = round(count / duration_sec, 2) if duration_sec > 0 else 0.0
                keys_list = topic_keys_cache.get(topic_name, [])
                topics_info.append({
                    'topic_metadata': {
                        'name': topic_name,
                        'message_count': count,
                        'available_keys': keys_list,
                        'ai_features': {'avg_frequency_hz': freq, 'active_in_slice': True}
                    }
                })

        metadata_content = {
            'rosbag2_bagfile_information': {
                'version': 9, 'storage_identifier': 'mcap',
                'duration': {'nanoseconds': int(duration_sec * 1e9)},
                'starting_time': {'nanoseconds_since_epoch': start_time_ns},
                'message_count': total_messages,
                'topics_with_message_count': topics_info,
                'files': [{'path': 'rosbag2.mcap', 'message_count': total_messages}]
            }
        }
        with open(metadata_path, 'w', encoding='utf-8') as mf:
            yaml.dump(metadata_content, mf, default_flow_style=False)

        print(f"    [OK] 切片完成 -> 輸出至 {output_bag_name} (共 {total_messages} 筆訊息)")

    print(f"\n[ALL DONE] 所有標記點切片完畢！")

if __name__ == "__main__":
    main()