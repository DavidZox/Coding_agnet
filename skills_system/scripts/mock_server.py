"""fih_rmf_system web_console 的離線替身：直接跑評測沙盒的 rmf_sim（--no-ros：orchestrtor／distribute／機器人的狀態機＋web_console＋
manual_trigger，不需要 ROS 2）。

以前這裡是另一份獨立的替身，已經跟真的系統脫節（/api/stations 回名稱、快照欄位不同、WebSocket 不 ping、120 秒就斷）；rmf_sim 照
amr_base/src/fih_rmf_system（orchestrator.py、resource_allocator.py、msg_codec.py、web_console）維護，技能的自我測試
（evals/skills/rmf_test.py）也用它，所以只留一份。
    python3 skills_system/scripts/mock_server.py [--port 8021] [--trigger-port 8003] [--config 設定.json] [rmf_sim.py 的其他參數]
預設只綁 127.0.0.1、port 8021／8003（避開真的 web_console 8020 與 manual_trigger 8002，它們的容器是 network_mode: host）。
技能用 --url http://127.0.0.1:8021（或環境變數 RMF_WEB_CONSOLE_URL）指過來，rmf_handshake 另外 --trigger http://127.0.0.1:8003
（或 RMF_MANUAL_TRIGGER_URL）。設定檔的格式見 rmf_sim.py 的說明（機器人行為、預先放的工作包、拓譜圖、參數）。
"""
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = os.path.join(PROJECT, "evals", "ops", "dataset", "sandbox", "rmf_sim", "rmf_sim.py")


def main(argv):
    if not os.path.isfile(SIM):
        print(f"[ERROR] 找不到 {SIM}（評測沙盒的 rmf_sim）。下一步：確認專案的 evals/ 目錄完整。")
        return 1
    args, i = [], 0
    while i < len(argv):
        if argv[i] == "--port" and i + 1 < len(argv):           # 舊的參數名稱
            args += ["--web-port", argv[i + 1]]
            i += 2
            continue
        args.append(argv[i])
        i += 1
    defaults = []
    if "--host" not in args:
        defaults += ["--host", "127.0.0.1"]
    if "--web-port" not in args:
        defaults += ["--web-port", "8021"]
    if "--trigger-port" not in args:
        defaults += ["--trigger-port", "8003"]
    os.execv(sys.executable, [sys.executable, SIM, "--no-ros", *defaults, *args])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
