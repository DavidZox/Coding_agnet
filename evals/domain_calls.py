"""評測的 worker（evals/chat/worker.py、evals/ops/worker.py）共用：主模型「交給領域」的那一步怎麼收尾、怎麼記。

- 中階要問使用者（參數）時：評測裡沒有人回答，取消（記下問了什麼）；取消之後的結果才是這一步的結果（跟使用者按取消一樣：中階取消之後
  接著開子工作階段一步一步做）。確認關卡（子工作階段或中階的低階碰到會改狀態的工具）照情境的 guard 回答（approve 同意、deny 不同意），
  跟主對話的確認關卡一樣算進 guards。
- 記成 tool_calls：分工的每個領域一筆（skill＝領域名稱，附子目標、項目、中階、子工作階段或公佈欄的狀態與做法、工作編號、那個領域的結果 #編號），
  領域裡用到的工具各一筆（via＝領域；中階的參數照每一版的圖，從收據帶入的不列；子工作階段的是每一步執行的）——情境的「用了哪個工具」照樣
  看得到領域裡用的工具。分工沒過核對（[ERROR]）時每個領域一筆、狀態 ERROR。
- 依報告回答（4-2）：這一步的 answers 與核對的結果記進那一步（record_answers）；最後的回答換成程式照項目排好的那一份（finalize：
  使用者看到的就是它，評測照它計分）。"""


def settle(agent, parsed, result, turn, guard="approve"):
    """中階或子工作階段還在等使用者回答：確認關卡照情境的 guard 回答（算進 guards），問參數就取消（評測沒有人回答）。回傳最後的結果。"""
    while agent.domain_pending:
        p = agent.domain_pending
        turn.setdefault("domain_asks", []).append(p["question"])
        if p["kind"] == "guard":
            if isinstance(turn.get("guards"), list):         # 主對話的評測記每一次的關卡；維運記次數
                turn["guards"].append(dict(p.get("guard") or {}, via=p["domain"]))
            else:
                turn["guards"] = turn.get("guards", 0) + 1
            result = agent.answer_domain("是" if guard == "approve" else "否")
        else:
            result = agent.cancel_domain()
        result = result if result is not None else ""
    return result


def calls(agent, parsed, result):
    """分工的這一步 → tool_calls 的紀錄（核對沒過的 [ERROR]：每個領域一筆、沒有執行）。分工照順序做完，這一次的紀錄是這一回合交給領域的
    最後幾筆（每個領域一筆）。"""
    entries = parsed["action"]["domains"]
    status = "ERROR" if result.lstrip().startswith(("[ERROR]", "[DENIED]")) else "PASS"
    dispatches = agent._domain_turn["dispatches"]
    run = dispatches[-len(entries):] if status == "PASS" and len(dispatches) >= len(entries) else []
    out = []
    for k, e in enumerate(entries):
        entry = {"script": None, "skill": e["domain"], "domain": e["domain"], "goal": e.get("goal", ""), "items": e.get("items") or [],
                 "args": [e.get("goal", "")] + list(e.get("items") or []), "status": status, "result_id": None}
        d = run[k] if run and run[k]["domain"] == e["domain"] else None
        if d is None:
            out.append(entry)
            continue
        entry["result_id"] = d.get("result_id")
        mid_part = d.get("mid") or (d if d.get("kind") == "mid" else None)       # 中階（中階沒做完接著開子工作階段時兩個都有）
        if mid_part:
            entry.update(mid_status=mid_part["status"], mid_skill=mid_part["skill"], mid_job=mid_part["job"])
        if d.get("kind") == "sub":
            entry.update(sub_status=d["status"], sub_job=d["job"], sub_steps=len(d.get("calls") or []))
        if d.get("kind") == "board":                                             # 方向的實驗：公佈欄的 worker
            entry.update(board_status=d["status"], board_job=d["job"], board_steps=len(d.get("calls") or []))
        via = [{"script": None, "skill": c["tool"], "via": e["domain"], "args": c["args"], "status": "PASS"}
               for c in (mid_part or {}).get("calls") or []]
        via += [{"script": c.get("script"), "skill": c["tool"], "via": e["domain"], "args": c["args"], "status": c["status"],
                 "head": c.get("head", "")} for c in (d.get("calls") or [] if d.get("kind") in ("sub", "board") else [])]
        out += [entry] + via
    return out


def record_answers(agent, parsed, turn):
    """依報告回答的那一步：answers 與沒過核對的項目記進 turn 的最後一步（不是這種回答就不記）。"""
    if parsed.get("action") or not agent.domain_items():
        return
    turn["steps"][-1].update(answers=parsed.get("answers") or [],
                             answer_problems={str(k): v for k, v in agent._answer_problems(parsed).items()})


def finalize(agent, parsed, turn):
    """回合結束時：依報告回答的話，回傳程式照項目排好的回答（也寫進最後一步的 reply）；不是就回 None。"""
    rendered = agent.domain_render(parsed)
    if rendered is not None:
        turn["steps"][-1]["reply"] = rendered
    return rendered
