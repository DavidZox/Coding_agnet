"""overpending_cancel：刪除卡在 distribute OverPending 逾時區的單站工作項——web_console DELETE /api/overpending_tasks/{id}
→ CancelOverpendingTask。

OverPending 不是終點：工作項在 raw 等超過 threshold_ovp_sec（預設 10 秒）或授權逾時就進 OverPending，待滿 threshold_recovery_sec
（預設 10 秒）又回流 raw，直到有機器人領走。distribute 只刪「此刻在 OverPending」的，而 DELETE 一律回 200，所以：
  1. 先看快照：此刻在 OverPending 才送；在 raw／processing 時回報所在的佇列（加 --wait 秒 會持續收幀，等它進來立刻刪）；
  2. 送出後讀快照確認全部的佇列：消失＝刪掉了；回到 raw／processing、或被機器人領走＝DELETE 晚到一步、沒刪到（[ERROR]，建議 --wait 重試）。
工作項 id 形如 <package>::<輪>::<站>::<run_id>-<序>（workpackage_status 查）。取消整個工作包是 workpackage_cancel。共用層見 _rmf_common.py。
"""
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rmf_common as rc   # noqa: E402

USAGE = (
    "用法: scripts/overpending_cancel_cmd.py <工作項id> [--wait 秒] [--url 位址]\n"
    "  工作項 id 形如 <package>::<輪>::<站>::<run_id>-<序>（workpackage_status 查）。\n"
    f"  --wait 秒（1～{rc.MAX_WATCH_SECONDS}）：此刻不在 OverPending 時等它進來再刪；不加就只看一幀、不在就回報。"
)


def parse_args(argv):
    """純函式：回傳 dict（error、task_id、wait、url）。"""
    pos, opts, err = rc.parse_cli(argv, values={"--wait": "秒數（1～300）", "--url": "web_console 位址（例如 http://localhost:8020）"},
                                  elsewhere={"--watch": "workpackage_status", "--cancel": "workpackage_cancel"}, usage=USAGE)
    if err:
        return {"error": err}
    if len(pos) != 1:
        return {"error": f"[ERROR] 需要 1 個工作項 id，收到 {len(pos)} 個（一次刪一筆，多筆就分開執行）。\n{USAGE}"}
    wait = None
    if "--wait" in opts:
        wait, err = rc.parse_seconds(opts["--wait"], "--wait")
        if err:
            return {"error": f"{err}只看一幀就不要加 --wait。"}
    url, err = rc.resolve_url(opts.get("--url"))
    if err:
        return {"error": err}
    return {"error": None, "task_id": pos[0].strip(), "wait": wait, "url": url}


def _taken_by(data, task_id):
    """distribute 已 confirm 給哪台機器人（網頁的 last_task_id 是最後領取的工作項）。"""
    return next((rid for rid, info in ((data or {}).get("robots") or {}).items() if (info or {}).get("last_task_id") == task_id), None)


def _not_found(task_id, data):
    owner = rc.item_package(data, task_id)
    if owner:
        cur = owner.get("current_item") or {}
        rid = cur.get("robot_id") or _taken_by(data, task_id)
        return (f"[PASS] 未刪除：{task_id} 已經不在 distribute（{'distribute 已 confirm 給 ' + rid if rid else '已離開 distribute 的佇列'}），"
                f"不能從 OverPending 刪除。它是 {owner.get('package_id')} 目前的工作項；要停止這個工作包（不再派下一站）用 "
                f"workpackage_cancel {owner.get('package_id')}。")
    pkg = rc.find_package(data, task_id)
    if pkg:
        cur = pkg.get("current_item") or {}
        iid = cur.get("item_id")
        label, t = rc.queue_of(data, iid) if iid else (None, None)
        return (f"[ERROR] {task_id} 是 work package 的 id，不是工作項 id。它目前的工作項是 {iid or '（還沒派出）'}"
                + (f"（distribute {rc.queue_text(label, t)}）" if label else "")
                + f"。下一步：刪 OverPending 裡的那一筆用 overpending_cancel {iid or '<工作項id>'}；取消整個工作包用 workpackage_cancel {task_id}。")
    ids = rc.item_ids(data)
    close = rc.close_matches(task_id, ids + [(p.get("current_item") or {}).get("item_id") for p in rc.packages(data)])
    ovp = rc._ids(data, "overpending_tasks")
    return (f"[ERROR] 找不到工作項 {task_id}：不在 distribute 的任何佇列，也不是任何工作包目前的工作項"
            + (f"（相近的：{'、'.join(close)}）" if close else "")
            + f"。此刻 OverPending 裡有 {len(ovp)} 筆" + (f"：{'、'.join(ovp[:8])}" if ovp else "")
            + "。下一步：工作項 id 會隨站點推進改變，用 workpackage_status <工作包> 查目前的；使用者給的 id 對不上就問使用者。")


def _observed(path):
    """觀察期間經過的佇列：raw（+0.0s）→ OverPending（+10.5s）。"""
    return " → ".join(f"{label or '不在佇列'}（{rc.fmt_s(t)}）" for t, label in path)


def cancel_overpending(task_id, wait, base):
    path, where, entry, data, t = [], None, None, None, 0.0
    try:
        with rc.WsStream(base) as ws:
            for t, data in ws.frames(duration=wait):
                where, entry = rc.queue_of(data, task_id)
                if not path or path[-1][1] != where:
                    path.append((t, where))
                if where == "OverPending":
                    break
            early = ws.end_text()
    except rc._WsError as e:
        return str(e)
    if data is None:
        return "[ERROR] web_console 沒有送出任何快照。下一步：稍等幾秒再試一次；持續發生請使用者檢查 web_console。"
    if where != "OverPending":
        if where is None and len(path) == 1:
            return _not_found(task_id, data)
        seen = ("一幀快照" if wait is None else f"觀察 {t:.1f} 秒" + (f"：{_observed(path)}" if len(path) > 1 else "")
                + (f"；⚠️ 提早結束：{early}" if early else ""))
        if where is None:
            taken = _taken_by(data, task_id)
            return (f"[PASS] 未刪除：{task_id} 在觀察期間離開了 distribute（{'被 ' + taken + ' 領走' if taken else '不在任何佇列'}），"
                    f"沒有進 OverPending（{seen}）。下一步：用 workpackage_status 看它所屬工作包的進度。")
        return (f"[PASS] 未刪除：{task_id} 目前在 {rc.queue_text(where, entry)}，不在 OverPending 逾時區，此刻刪不掉（{seen}）。"
                f"工作項在 raw 等超過 threshold_ovp_sec（預設 10 秒）或授權逾時才會進 OverPending，之後 threshold_recovery_sec"
                f"（預設 10 秒）內就要刪。下一步：加 --wait 30 讓我等它進逾時區立刻刪；或用 workpackage_cancel 取消整個工作包。")
    waited = f"（等了 {t:.1f} 秒它才進入逾時區）" if len(path) > 1 else ""
    status, text, err = rc._http("DELETE", base, f"/api/overpending_tasks/{quote(task_id, safe='')}")
    if err:
        return err

    def check(d):
        label, _ = rc.queue_of(d, task_id)
        if label is None:
            rid = _taken_by(d, task_id)
            return f"taken:{rid}" if rid else "gone"
        return None if label == "OverPending" else f"back:{label}"

    verdict, last, ct, cerr = rc.confirm_after(base, check)
    owner = task_id.split("::", 1)[0]
    if cerr:
        return (f"[ERROR] 已送出刪除 {task_id}（HTTP {status}），但讀不到快照確認結果：{cerr[8:]}\n"
                f"下一步：用 workpackage_status {owner} 確認它還在不在 OverPending。")
    if verdict == "gone":
        return (f"[PASS] 已刪除 OverPending 工作項 {task_id}{waited}：快照確認它已不在 distribute 的任何佇列（{rc.fmt_s(ct)}）\n"
                f"注意：orchestrtor 不知道這一站被刪了——工作包 {owner} 若還在 RUNNING，會一直等這一站的完成訊號（不會自動補派）；"
                f"不需要這個工作包就用 workpackage_cancel {owner}。")
    if verdict and verdict.startswith("back:"):
        label = verdict[5:]
        return (f"[ERROR] 沒有刪到 {task_id}：送出 DELETE（HTTP {status}）時它已經離開 OverPending、回到 {label}（distribute 只刪此刻在 "
                f"OverPending 的，晚到一步就不會刪）。下一步：執行 overpending_cancel {task_id} --wait 30，它下次進入 OverPending 時立刻刪；"
                f"或用 workpackage_cancel {owner} 取消整個工作包。")
    if verdict and verdict.startswith("taken:"):
        return (f"[ERROR] 沒有刪到 {task_id}：DELETE 送達前它已回流並被 {verdict[6:]} 領走（distribute 已 confirm），機器人會執行這一站。"
                f"下一步：要停止後面的站就用 workpackage_cancel {owner}。")
    return (f"[ERROR] 已送出刪除 {task_id}（HTTP {status}），但 {rc.CONFIRM_SECONDS:g} 秒內它仍在 OverPending：distribute 沒有處理"
            f"（沒在跑，或 cancel_overpending_task 沒送到）。下一步：用 workpackage_status {owner} 再確認一次；"
            f"一直存在就請使用者檢查 distribute 節點（ROS2_node_list 找 /distribute 或 /resource_allocator）。")


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    return cancel_overpending(p["task_id"], p["wait"], p["url"])


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] overpending_cancel 未預期的例外：{type(e).__name__}: {e}")
        sys.exit(1)
