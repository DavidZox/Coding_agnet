"""評測的 worker（evals/chat/worker.py、evals/ops/worker.py）共用：主模型「交給領域」的那一步怎麼收尾、怎麼記。

- 中階要問使用者時：評測裡沒有人回答，取消（記下問了什麼）；取消之後的結果才是這一步的結果（跟使用者按取消一樣）。
- 記成 tool_calls：交給領域本身一筆（skill＝領域名稱，附子目標、項目、中階的狀態與做法、工作編號），中階在領域裡用到的工具各一筆
  （via＝領域；參數照每一版的圖，從收據帶入的不列）——情境的「用了哪個工具」照樣看得到領域裡用的工具。"""


def settle(agent, parsed, result, turn):
    """中階還在等使用者回答就取消（評測沒有人回答）。回傳最後的結果。"""
    while agent.domain_pending:
        turn.setdefault("domain_asks", []).append(agent.domain_pending["question"])
        result = agent.cancel_domain()
    return result


def calls(agent, parsed, result):
    """交給領域的這一步 → tool_calls 的紀錄（核對沒過的 [ERROR] 只有一筆）。"""
    action = parsed["action"]
    status = "ERROR" if result.lstrip().startswith(("[ERROR]", "[DENIED]")) else "PASS"
    entry = {"script": None, "skill": action["domain"], "domain": action["domain"], "goal": action.get("goal", ""),
             "items": action.get("items") or [], "args": [action.get("goal", "")] + list(action.get("items") or []),
             "status": status, "result_id": agent.last_result_id}
    dispatches = agent._domain_turn["dispatches"]
    if status == "ERROR" or not dispatches:
        return [entry]
    d = dispatches[-1]
    entry.update(mid_status=d["status"], mid_skill=d["skill"], mid_job=d["job"])
    return [entry] + [{"script": None, "skill": c["tool"], "via": action["domain"], "args": c["args"], "status": "PASS"}
                      for c in d.get("calls") or []]
