"""調查與整理報告的情境（第 5 階段，2026-10-25）：要查好幾個地方（調度系統、容器、log、設定）才答得出來的調查（domain＝investigate），
與從好幾個地方收集資料、寫成檔案的報告（domain＝report）。跟 scenarios.py 同一套格式與計分，答案由沙盒的內容事先算好
（fs_world 的檔案、rmf_sim 的設定、容器的腳本），不靠人工判斷。

名稱開頭 inv_：phase_check 的總分另外算一組，主要 50、保留 20 照舊可以跟以前的基準比。報告的檢查看檔案裡要有使用者要的每一項
（每台機器人、每個容器、每一則錯誤的時間），不是只看有沒有寫檔。
"""
import re

import fs_world
from scenarios import DOCKER_SET, NO_FS_WRITE, NO_REPLY, REPLIED_NO, ROBOTS3, S, pkg, sim


def _errors(day):
    """logs/<day>/ 裡每一則 ERROR：[(時間, 機器人, 錯誤碼)]，依時間排序。"""
    out = []
    for rel, (text, _) in sorted(fs_world.files().items()):
        if rel.startswith(f"logs/{day}/"):
            for ln in text.splitlines():
                m = re.match(rf"{day} (\S+) \[ERROR\] (\S+) (E\d+)", ln)
                if m:
                    out.append(m.groups())
    return sorted(out)


ERR_1010 = _errors("2026-10-10")
E2001_TB3 = next(t for t, r, c in ERR_1010 if r == "tb3" and c == "E2001")
NOT_THERE = (r"site_b[^\n]{0,40}(還沒|尚未|沒有|不存在|找不到|not found)", r"(還沒|尚未|沒有|不存在|找不到)[^\n]{0,30}site_b")

INVESTIGATE = [
    # ================================================================ 調查（只查不改）
    S("inv_two_stuck", "investigate", "WP_P1 跟 WP_P2 都一直沒有完成，分別查一下各是什麼原因。先不要改任何東西。",
      [("reply_all", "WP_P1", "WP_P2", "tb2", "tb3"), ("reply_any", *NO_REPLY), ("reply_re_any", *REPLIED_NO)],
      world={"sim": sim(robots_=[ROBOTS3[0], dict(ROBOTS3[1], behavior="silent"), dict(ROBOTS3[2], behavior="busy")],
                        packages=[pkg("WP_P1", "tb2", "a3"), pkg("WP_P2", "tb3", "a6")]), "wait": 8},
      forbid=("sim_changed",), note="兩個工作包各一個原因：tb2 不回應授權、tb3 一直回 no"),
    S("inv_nav2_map", "investigate", "nav2_test 一直起不來。查清楚它要載入的是哪一張地圖、我們工作區的 maps/ 裡有哪些地圖，說明原因。不要改任何東西。",
      [("reply_all", "site_b", "site_a"), ("reply_re_any", *NOT_THERE)],
      world={"containers": DOCKER_SET}, forbid=("docker_changed_any", *NO_FS_WRITE),
      note="容器的 log（要 /maps/site_b.yaml）＋工作區的 maps/（只有 site_a，README 寫 site_b 還沒建）"),
    S("inv_battery_threshold", "investigate",
      "哪幾台機器人現在的電量已經低於 configs/robots.yaml 裡它自己的 battery_low？列出每台的電量與門檻。不要改任何東西。",
      [("reply_all", "tb2", "tb3"),
       ("reply_re", r"(?<![\d.])18\.5(?![\d])", r"(?<![\d.])24(\.0)?(?![\d.])", r"(?<![\d.])20(?![\d.])", r"(?<![\d.])25(?![\d.])")],
      world={"sim": sim(robots_=[dict(ROBOTS3[0], battery=22.0), dict(ROBOTS3[1], battery=18.5), dict(ROBOTS3[2], battery=24.0)])},
      forbid=("sim_changed", *NO_FS_WRITE), note="即時的電量（tb1 22、tb2 18.5、tb3 24）對照設定的門檻（20、20、25）：tb2、tb3 低於"),
    S("inv_e2001_now", "investigate",
      "tb3 今天（2026-10-10）的 log 有沒有出現電池電壓下降（E2001）？是幾點？它現在的電量是多少、停在哪一站？不要改任何東西。",
      [("reply_all", E2001_TB3, "a8"), ("reply_re", r"(?<![\d.])64(\.0)?(?![\d.])")],
      world={"sim": sim()}, forbid=("sim_changed", *NO_FS_WRITE), note="log 檔＋調度系統的即時狀態"),

    # ================================================================ 整理報告（寫成檔案）
    S("inv_fleet_report", "report",
      "整理一份機隊現況寫到 reports/fleet_status.md：每台機器人現在的電量、停在哪一站，加上 configs/robots.yaml 裡它的 max_speed。",
      [("fs_contains", "reports/fleet_status.md", "tb1", "tb2", "tb3", "82", "76.5", "64", "home", "a0", "a8", "0.8", "0.7", "0.55")],
      world={"sim": sim()}, forbid=("sim_changed", ("fs_changed_outside", ["reports/fleet_status.md"]))),
    S("inv_error_timeline", "report",
      "把 logs/2026-10-10/ 裡每台機器人的 ERROR 依時間整理成時間線，寫到 reports/errors_1010.md（每一則要有時間、機器人與錯誤碼）。",
      [("fs_contains", "reports/errors_1010.md", *[t for t, _, _ in ERR_1010], "E1203", "E2001", "tb1", "tb3")],
      forbid=(("fs_changed_outside", ["reports/errors_1010.md"]),), note=f"{len(ERR_1010)} 則（tb1 1 則、tb3 6 則）"),
    S("inv_container_report", "report",
      "整理目前所有容器的狀態寫到 reports/containers.md：每個容器在跑還是停了；停掉的寫結束碼與停掉的原因（看它的 log）。",
      [("fs_contains", "reports/containers.md", "web_cache", "log_writer", "nav2_test", "db_backup", "scratch_tools", "site_b"),
       ("fs_contains_any", "reports/containers.md", "128 rows", "backup finished")],
      world={"containers": DOCKER_SET}, forbid=("docker_changed_any", ("fs_changed_outside", ["reports/containers.md"]))),
]

BY_ID = {s["id"]: s for s in INVESTIGATE}
assert len(BY_ID) == len(INVESTIGATE) and all(s["id"].startswith("inv_") for s in INVESTIGATE)
