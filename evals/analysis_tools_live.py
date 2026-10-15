"""ROS 2 數據技能的實機測試：在真的容器裡，對真的實驗資料夾跑 mcap_analyzer／rosout_parser／mcap_feature_measure／mcap_slicer
（--record 再加 mcap_recorder），檢查輸出格式與錯誤處理。不需要 Ollama。

    python3 evals/analysis_tools_live.py --container ros2_web_container \\
        --data /workspace/app/diagnostics_package/toolkit/experiment_logs/exp_20261014_084506 [--record]

切片與錄製都寫到容器的 /tmp（測完刪掉），不會在實驗資料夾留下切片；mcap_analyzer 第一次讀一份數據時會在它的 bag 資料夾
建立 topic_metadata.json／.yaml（全域索引的快取，這是工具本來的行為）。"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills_system", "scripts")


def run(script, *args, env=None):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True, timeout=600,
                       env=dict(os.environ, **(env or {})))
    return (r.stdout or "") + (r.stderr or "")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--container", required=True)
    p.add_argument("--data", required=True, help="容器內的實驗資料夾、bag 資料夾或 .mcap")
    p.add_argument("--record", action="store_true", help="另外真的錄 6 秒（容器裡要有正在發布的 Topic）")
    a = p.parse_args()
    env = {"TARGET_CONTAINER": a.container, "ANALYSIS_DATA": ""}
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(("✅ " if ok else "❌ ") + name + ("" if ok else f"\n   {detail[:1200]}"))

    out = run("mcap_analyzer_cmd.py", a.data, "--json", env=env)
    try:
        idx = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except ValueError:
        idx = None
    check("mcap_analyzer --json：全域 Topic Metadata（時間範圍、Topic、角色、Key）", bool(idx and idx.get("topics")), out)
    if not idx:
        sys.exit(1)
    workers = [t for t in idx["topics"] if t["role"] == "worker"]
    check("至少一個 worker 可分析的 Topic（訊息型別解得開）", bool(workers), json.dumps(idx["topics"], ensure_ascii=False)[:800])
    out = run("mcap_analyzer_cmd.py", a.data, env=env)
    check("mcap_analyzer：總表與 [ANALYSIS_DATA] 標記", out.startswith("[PASS] Topic Metadata") and "[ANALYSIS_DATA]" in out, out)
    if workers:
        t = workers[0]
        key = next((k for k in t["keys"] if k["category"] in ("state", "numeric", "vector")), None)
        out = run("mcap_analyzer_cmd.py", a.data, "--topic", t["topic"], env=env)
        check(f"mcap_analyzer --topic {t['topic']}：Key 的型別、維度、類別", out.startswith("[PASS]") and "Key｜ROS 型別" in out, out)
        if key:
            out = run("mcap_feature_measure_cmd.py", a.data, "--topic", t["topic"], "--key", key["key"], env=env)
            check(f"mcap_feature_measure {t['topic']} {key['key']}：特徵與異常指標", out.startswith("[PASS] 特徵量測")
                  and f"▸ {key['key']}（" in out and "異常指標（程式判斷）" in out, out)
            out = run("mcap_feature_measure_cmd.py", a.data, "--topic", t["topic"], "--key", key["key"], "--window", "+0~+5s", env=env)
            check("時間窗的寬鬆寫法（+0~+5s）", out.startswith("[PASS]") and "+0.00s ～ +5.00s" in out, out)
            out = run("mcap_feature_measure_cmd.py", a.data, "--topic", t["topic"], "--key", key["key"], "--bogus", "1", env=env)
            check("不認識的參數：照認得的做完、附上說明", out.startswith("[PASS]") and "已忽略不認識的參數：--bogus 1" in out, out)
            out = run("mcap_analyzer_cmd.py", a.data, "--topic", t["topic"], "--key", key["key"], "--preview", "3", env=env)
            check("mcap_analyzer --key --preview：原始值", out.startswith("[PASS]") and "前 " in out, out)
        out = run("mcap_feature_measure_cmd.py", a.data, "--topic", "/no_such_topic", "--key", "x", env=env)
        check("不存在的 Topic：[ERROR] 並列出有的 Topic", out.startswith("[ERROR]") and t["topic"] in out, out)
    out = run("rosout_parser_cmd.py", a.data, "--json", env=env)
    try:
        logs = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except ValueError:
        logs = None
    has_log = any(t["role"] == "log" for t in idx["topics"]) or idx.get("rosout_log")
    check("rosout_parser --json：唯一訊號（L#、層級、次數、時間戳）", (logs is not None and "signals" in logs) or not has_log, out)
    if logs and logs["signals"]:
        sid = logs["signals"][0]["id"]
        out = run("mcap_slicer_cmd.py", a.data, "--signal", sid, "--before", "0.5", "--after", "1", "--out", "/tmp/agent_live_slices", env=env)
        check(f"mcap_slicer --signal {sid}：toolkit 格式的切片", out.startswith("[PASS] 切片完成") and "sliced_bag_1_" in out, out)
        slice_dir = next((ln.strip() for ln in out.splitlines() if ln.strip().startswith("/tmp/agent_live_slices/sliced_bag_")), "")
        if slice_dir:
            out = run("mcap_analyzer_cmd.py", slice_dir, env=env)
            check("切片本身也是數據（檔案級 Metadata ai_slice_diagnostic_summary）", out.startswith("[PASS]")
                  and "ai_slice_diagnostic_summary" in out, out)
    out = run("mcap_slicer_cmd.py", a.data, "--at", "+999999", "--out", "/tmp/agent_live_slices", env=env)
    check("時間點不在數據範圍內：不切、回錯誤", out.startswith("[ERROR]") and "不在數據範圍內" in out, out)
    # analysis_run 的動態時間切片：明確的時間窗、只切指定的 Topic、帶時間窗之前的最後一則；讀切片量到的要跟讀原本的數據一樣
    st = next((t for t in workers if any(k["category"] == "state" for k in t["keys"])), None)
    if st:
        skey = next(k["key"] for k in st["keys"] if k["category"] == "state")
        span = (idx["end_ns"] - idx["start_ns"]) / 1e9
        out = run("mcap_slicer_cmd.py", a.data, "--window", f"+{span * 0.4:.2f},+{span * 0.9:.2f},,W1", "--topics", st["topic"],
                  "--with-state", "--out", "/tmp/agent_live_slices", "--json", env=env)
        try:
            sj = json.loads(out[out.index("{"):out.rindex("}") + 1])["slices"][0]
        except (ValueError, KeyError, IndexError):
            sj = None
        check(f"mcap_slicer --window --topics --with-state：只切 {st['topic']}、帶時間窗之前的最後一則",
              bool(sj) and set(sj["topics"]) == {st["topic"]} and sj["trigger"]["id"] == "W1", out)
        if sj:
            win = {"id": "W1", "start_ns": int(round(sj["start_sec"] * 1e9)), "end_ns": int(round(sj["end_sec"] * 1e9)), "anchor_ns": None}
            outs = [run("mcap_feature_measure_cmd.py", a.data, "--topic", st["topic"], "--key", skey, "--window", "W1",
                        env=dict(env, ANALYSIS_WINDOWS=json.dumps([w]))) for w in (dict(win, slice=sj["dir"]), win)]
            body = [[ln for ln in o.splitlines()[2:] if not ln.startswith("[")] for o in outs]
            check(f"讀切片量到的＝讀原本的數據（{skey}：筆數、跳轉、沿用的狀態都一樣，只多「讀切片」）",
                  "讀切片" in outs[0] and outs[0].startswith("[PASS]") and body[0] == body[1], outs[0] + "\n----\n" + outs[1])
    if a.record and workers:
        out = run("mcap_recorder_cmd.py", "--topics", workers[0]["topic"], "--duration", "6", "--out-root", "/tmp/agent_live_rec",
                  "--name", "exp_live", env=env)
        check("mcap_recorder：錄 6 秒、rosout.log、錄完建立索引", out.startswith("[PASS] 錄製完成") and "全域 Topic Metadata 索引" in out, out)
    subprocess.run(["docker", "exec", a.container, "rm", "-rf", "/tmp/agent_live_slices", "/tmp/agent_live_rec"], capture_output=True)
    print(f"\n{sum(results)}/{len(results)} 通過")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
