#!/usr/bin/env python3
import os
import sys

def parse_rosout_log(log_path):
    if not os.path.exists(log_path):
        print(f"[ERROR] 找不到日誌檔：{log_path}")
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
    if len(sys.argv) < 2:
        print("Usage: python3 rosout_parser.py <experiment_dir>")
        sys.exit(1)
        
    exp_dir = sys.argv[1]
    log_path = os.path.join(exp_dir, "rosout.log")
    
    events = parse_rosout_log(log_path)
    if not events:
        print("[WARN] rosout.log 中沒有解析到任何有效的事件記錄。")
        sys.exit(0)

    print(f"\n=== INFO / WARN / ERROR 標記檢視器 ===")
    levels = sorted(list(set(e['level'] for e in events)))
    for idx, lvl in enumerate(levels, 1):
        count = sum(1 for e in events if e['level'] == lvl)
        print(f" {idx}) {lvl} (共 {count} 筆)")
    print(f" 0) 顯示全部")
    
    choice = input("請選擇要查看的標記層級代號: ").strip()
    selected_level = None
    if choice != "0" and choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(levels):
            selected_level = levels[idx]

    filtered_events = [e for e in events if selected_level is None or e['level'] == selected_level]
    
    if not filtered_events:
        print("[ERROR] 沒有符合條件的事件。")
        sys.exit(1)

    print(f"\n{'No.':<4} | {'Level':<6} | {'Timestamp':<18} | {'Message Content'}")
    print("-" * 80)
    for idx, e in enumerate(filtered_events, 1):
        msg_preview = e['raw'].split(']: ', 1)[1] if ']: ' in e['raw'] else e['raw']
        if len(msg_preview) > 50:
            msg_preview = msg_preview[:47] + "..."
        print(f" {idx:<3} | {e['level']:<6} | {e['timestamp_str']:<18} | {msg_preview}")

if __name__ == "__main__":
    main()