"""workpackage_cancel：取消（刪除）一個 work package——web_console DELETE /api/work_packages/{id} → CancelWorkPackage。

DELETE 不論有沒有這個 id 都回 200，所以先讀快照確認它在 orchestrtor 的清單裡（不在就不送：打錯字不會回「已取消」）；送出後
讀快照確認它從清單消失。orchestrtor 只會停止派下一站、從清單移除；已經送到 distribute 的當前站可能仍會被機器人執行完
（回報裡寫那一站此刻在哪裡）。工作項 id（含 ::）不是工作包：只刪卡在 OverPending 的那一筆用 overpending_cancel。
共用層見 _rmf_common.py。
"""
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rmf_common as rc   # noqa: E402

USAGE = "用法: scripts/workpackage_cancel_cmd.py <task_id> [--url 位址]（task_id＝work package 的 id，用 workpackage_status 查）"


def parse_args(argv):
    """純函式：回傳 dict（error、task_id、url）。"""
    pos, opts, err = rc.parse_cli(argv, values={"--url": "web_console 位址（例如 http://localhost:8020）"},
                                  elsewhere={"--wait": "overpending_cancel", "--watch": "workpackage_status"}, usage=USAGE)
    if err:
        return {"error": err}
    if len(pos) != 1:
        return {"error": f"[ERROR] 需要 1 個參數 <task_id>，收到 {len(pos)} 個；一次取消一個工作包（多個就分開執行）。\n{USAGE}"}
    task_id = pos[0].strip()
    if "::" in task_id:
        pid = task_id.split("::", 1)[0]
        return {"error": (f"[ERROR] {task_id} 是 distribute 的工作項 id（work item），不是 work package 的 id。下一步：要取消整個工作包就執行 "
                          f"workpackage_cancel {pid}；只刪卡在 OverPending 逾時區的那一筆用 overpending_cancel {task_id}。")}
    url, err = rc.resolve_url(opts.get("--url"))
    if err:
        return {"error": err}
    return {"error": None, "task_id": task_id, "url": url}


def _current_note(pkg, data, topo):
    """取消時，目前那一站在哪裡：機器人可能仍會把它做完。"""
    cur = (pkg or {}).get("current_item") or {}
    if not cur or pkg.get("status") == "COMPLETED":
        return ""
    iid = cur.get("item_id")
    label, t = rc.queue_of(data, iid)
    station = rc.station_text(cur.get("station"), topo)
    if label == "OverPending":
        return f"目前那一站（{iid}，{station}）還在 distribute 的 OverPending：要它也不跑就用 overpending_cancel {iid}（它會在 OverPending 與 raw 之間來回）。"
    if label:
        return (f"目前那一站（{iid}，{station}）還在 distribute（{rc.queue_text(label, t)}）：distribute 不知道工作包取消了，"
                f"配到機器人時那一站仍可能被執行；它進入 OverPending 時可以用 overpending_cancel {iid} 刪。")
    if cur.get("status") == "DISPATCHED" and cur.get("robot_id"):
        return f"目前那一站（{iid}，{station}）已經交給 {cur['robot_id']}：機器人可能仍會跑完這一站，只是不會再派下一站。"
    return "目前那一站不在 distribute：之後不會再派任何站。"


def cancel(task_id, base):
    topo, _ = rc.fetch_topology(base)
    data, err = rc.ws_read_json(base)
    if err:
        return f"{err}\n（取消前要先從快照確認 {task_id} 存在；沒有送出取消。）"
    if not rc.orchestrtor_alive(data):
        return (f"[ERROR] 快照裡 orchestrtor 沒有回報過狀態（step_counter 0）：orchestrtor 可能沒在跑，沒辦法確認 {task_id} 存在、取消了也沒人處理；"
                f"沒有送出。下一步：請使用者確認 orchestrtor 節點（ROS2_node_list 找 /orchestrtor）。")
    pkg = rc.find_package(data, task_id)
    if not pkg:
        ids = [p.get("package_id") for p in rc.packages(data)]
        close = rc.close_matches(task_id, ids)
        stray = [i for i in rc.item_ids(data) if str(i).startswith(f"{task_id}::")]
        return (f"[ERROR] orchestrtor 的清單裡沒有 work package {task_id}，沒有送出取消"
                + (f"（相近的：{'、'.join(close)}）" if close else "")
                + f"：id 打錯、或已經取消過（取消後就從清單消失）。目前清單 {len(ids)} 個"
                + (f"：{'、'.join(map(str, ids[:15]))}{'…' if len(ids) > 15 else ''}" if ids else "")
                + "。下一步：用 workpackage_status 確認正確的 id；使用者給的 id 對不上就問使用者。"
                + (f"\ndistribute 裡還有它的工作項：{'、'.join(stray)}（工作包已不在清單；卡在 OverPending 的可以用 overpending_cancel 刪）" if stray else ""))
    before = f"{pkg.get('status')}，第 {(pkg.get('station_index') or 0) + 1}/{pkg.get('station_count')} 站"
    note = _current_note(pkg, data, topo)
    status, text, err = rc._http("DELETE", base, f"/api/work_packages/{quote(task_id, safe='')}")
    if err:
        return err
    verdict, last, t, cerr = rc.confirm_after(base, lambda d: "gone" if not rc.find_package(d, task_id) else None)
    if cerr:
        return (f"[ERROR] 已送出取消 {task_id}（HTTP {status}），但讀不到快照確認結果：{cerr[8:]}\n"
                f"下一步：稍後用 workpackage_status {task_id} 確認它已不在清單。")
    if verdict != "gone":
        return (f"[ERROR] 已送出取消 {task_id}（HTTP {status}），但 {rc.CONFIRM_SECONDS:g} 秒內它仍在 orchestrtor 的清單："
                f"orchestrtor 沒有處理（沒在跑，或 cancel_work_package 沒送到）。下一步：用 workpackage_status {task_id} 再確認一次；"
                f"一直存在就請使用者檢查 orchestrtor 節點（ROS2_node_list 找 /orchestrtor），不要一直重送。")
    done = "它已經 COMPLETED，取消只是從清單移除。" if pkg.get("status") == "COMPLETED" else note
    return (f"[PASS] 已取消 work package {task_id}（取消前 {before}）：快照確認已從 orchestrtor 的清單移除（{rc.fmt_s(t)}）\n"
            f"{done}\n注意：orchestrtor 只停止派下一站；要確認機器人那邊的狀況用 workpackage_status 或 rmf_handshake status <機器人>。")


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    return cancel(p["task_id"], p["url"])


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] workpackage_cancel 未預期的例外：{type(e).__name__}: {e}")
        sys.exit(1)
