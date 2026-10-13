#!/usr/bin/env python3
import sys
import signal

# 忽略 SIGPIPE 或正常捕捉 BrokenPipeError 以避免噴出 traceback
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

def parse_stream():
    buffer = []
    try:
        for line in sys.stdin:
            stripped_line = line.strip()
            if stripped_line == "---":
                if buffer:
                    process_doc("".join(buffer))
                    buffer = []
            else:
                # 排除可能混入的 file, function, line 欄位
                if not (stripped_line.startswith("file:") or 
                        stripped_line.startswith("function:") or 
                        stripped_line.startswith("line:")):
                    buffer.append(line)
        if buffer:
            process_doc("".join(buffer))
    except (BrokenPipeError, KeyboardInterrupt):
        sys.stderr = open("/dev/null", "w")
        sys.exit(0)

def process_doc(doc_str):
    try:
        sec, nanosec, level_num, name, msg = 0, 0, 20, "unknown", ""
        in_msg = False
        msg_lines = []

        for line in doc_str.splitlines():
            stripped = line.strip()
            if stripped.startswith("sec:"):
                sec = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("nanosec:"):
                nanosec = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("level:"):
                level_num = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("name:"):
                name = stripped.split(":", 1)[1].strip().strip("\x27\x22")
            elif stripped.startswith("msg:"):
                in_msg = True
                msg_val = stripped.split(":", 1)[1].strip()
                if (msg_val.startswith("\x27") and msg_val.endswith("\x27")) or (msg_val.startswith("\x22") and msg_val.endswith("\x22")):
                    msg_val = msg_val[1:-1]
                msg_lines.append(msg_val)
            elif in_msg:
                if not (stripped.startswith("file:") or stripped.startswith("function:") or stripped.startswith("line:")):
                    msg_lines.append(line.rstrip())

        timestamp = f"{sec}.{nanosec:09d}"
        level_map = {10: "DEBUG", 20: "INFO", 30: "WARN", 40: "ERROR", 50: "FATAL"}
        level_str = level_map.get(level_num, "INFO")
        final_msg = "\n".join(msg_lines).strip()

        print(f"[{level_str}] [{timestamp}] [{name}]: {final_msg}")
        sys.stdout.flush()
    except Exception:
        pass

if __name__ == "__main__":
    parse_stream()