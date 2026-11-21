"""真實專案評測的題目：五種，各 5 題，另外各 1 題當保留組（共 30 題）。答案由程式從快照算（evals/repo/snapshot.py），
存成 evals/repo/answers.json；核對的規則在 evals/repo/checks.py。

    python3 evals/repo/questions.py --write    # 解開快照、算每一題的答案，寫 answers.json
    python3 evals/repo/questions.py --check    # 重算一次，跟 answers.json 比

agent 的工作目錄是快照的 amr_base/src（底下是 amr_base_sw、amr_base_hw、fih_rmf_system）。每一題的 compute(root) 回傳：
- answer：給人看的答案；
- items：回覆裡要有的事實。每一則是幾組寫法（`all`：每一組都要出現，組內任一個寫法就算）；`file`：第一組是檔名，其他組寫在
  它那一行或它後面、下一個檔名之前（檔名與行號、檔名與次數）；`line`：寫在同一行（參數與預設值、總數）；`near`：在多少字以內
  （規格書的編號與它的內容）；
- forbid：出現就算錯的（例如限定範圍的題目答成整個目錄的總數）。
算答案時順便檢查題目本身沒有歧義：定義只有一個、grep 跟 AST 數到的一樣、規格書那一列真的寫了那些字；不成立就丟例外，換題目。

保留組（set="holdout"）量沒看過的情境：不要照保留組的內容調 prompt、技能說明或複合技能。
"""
import argparse
import ast
import collections
import io
import json
import os
import re
import sys
import tempfile
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ANSWERS = os.path.join(HERE, "answers.json")
KINDS = {"count": "限定範圍的找檔案與計數", "doc": "讀長文件回答", "python": "Python 的定義與呼叫",
         "cpp": "C++（靠搜尋與看檔）", "cross": "跨檔案的調查"}
TOTAL = ("共", "總", "合計", "加起來", "total")


# ---- 讀快照的小工具 ----

def _read(root, rel):
    with open(os.path.join(root, rel), "rb") as f:
        data = f.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:          # sick_scan_xd 有幾個 C++ 檔是 Latin-1
        return data.decode("latin-1")


def _lines(root, rel):
    return _read(root, rel).split("\n")


def _py(root, scope):
    """scope 底下每個 .py →（相對路徑, AST, 原文）。"""
    for dp, dns, fns in os.walk(os.path.join(root, scope)):
        dns.sort()
        for fn in sorted(fns):
            if fn.endswith(".py"):
                rel = os.path.relpath(os.path.join(dp, fn), root)
                src = _read(root, rel)
                yield rel, ast.parse(src), src


def _line_of(root, rel, pattern):
    """rel 裡唯一符合 pattern（正規表示式）的行號。"""
    hits = [i for i, ln in enumerate(_lines(root, rel), 1) if re.search(pattern, ln)]
    assert len(hits) == 1, (rel, pattern, hits)
    return hits[0]


def _row(root, rel, row_id, *must):
    """規格書表格裡編號 row_id 那一列：（行號, 可以當出處的編號）；那一列要寫了 must 的每一段字。
    出處收這一列的編號，加上列裡寫到的同一份規格書的編號（TSK-S08 那一列寫了分支 TSK-F23-B04）：引用哪一個都對。"""
    n = _line_of(root, rel, rf"^\|\s*{re.escape(row_id)}\s*\|")
    row = _lines(root, rel)[n - 1]
    for m in must:
        assert m in row, (row_id, m, row[:200])
    prefix = row_id.split("-")[0]
    return n, [row_id] + sorted(set(re.findall(rf"\b{prefix}-[A-Z]\d+(?:-B\d+)?\b", row)) - {row_id})


NEG = "[^。，,；;\n]{0,6}"   # 否定詞到動詞之間的字（「不會進行回報」「不重新開始計時」），不跨過標點


def _calls_by_file(root, scope, attr):
    c = collections.Counter()
    for rel, tree, src in _py(root, scope):
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr:
                c[rel] += 1
        grep = len(re.findall(rf"\b{attr}\s*\(", src))
        assert grep == c[rel], (rel, attr, "AST", c[rel], "grep", grep)   # 註解或字串裡也有就有歧義
    return +c


def _text_mentions(src, pattern):
    """pattern 出現在註解或字串（含 docstring）裡的行號。"""
    kinds = {tokenize.COMMENT, tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}
    out = set()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in kinds:
            out |= {tok.start[0] + k for k, ln in enumerate(tok.string.split("\n")) if re.search(pattern, ln)}
    return out


def _def_and_callers(root, scope, name):
    """名稱唯一的函式或方法：定義（檔案, 行, 類別）與呼叫的地方 [(檔案, 行)]。grep 看到的每一行都要是其中之一，
    或是註解、字串裡提到它（例如 docstring 寫「solve_conflicts() 依序嘗試」）——那些行不算呼叫，答了也不扣分。"""
    defs, calls, grep, text = [], set(), set(), set()
    for rel, tree, src in _py(root, scope):
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef):
                defs += [(rel, b.lineno, n.name) for b in n.body if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name == name]
            elif isinstance(n, ast.Call):
                f = n.func
                if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)) == name:
                    calls.add((rel, n.lineno))
        defs += [(rel, n.lineno, None) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        grep |= {(rel, i) for i, ln in enumerate(src.split("\n"), 1) if re.search(rf"\b{name}\s*\(", ln)}
        text |= {(rel, i) for i in _text_mentions(src, rf"\b{name}\s*\(")}
    assert len(defs) == 1, (name, defs)
    assert grep - text == calls | {defs[0][:2]}, (name, sorted((grep - text) ^ (calls | {defs[0][:2]})))
    return defs[0], sorted(calls)


def _short(path, others):
    """檔名；同一題裡有同名的檔案時連上一層目錄。"""
    base = os.path.basename(path)
    if sum(1 for p in set(others) if os.path.basename(p) == base) > 1:
        return "/".join(path.split("/")[-2:])
    return base


def g(*alts):
    return list(alts)


def item(label, *groups, near=None, line=False, file=False):
    return {"label": label, "all": [list(x) for x in groups], "near": near, "line": line, "file": file}


def _file_line(path, line, others=()):
    name = _short(path, others or [path])
    return item(f"{name}:{line}", g(name), g(str(line)), file=True)


def _counts(c):
    files = list(c)
    out = [item(f"{_short(p, files)}：{n}", g(_short(p, files)), g(str(n)), file=True) for p, n in sorted(c.items())]
    out.append(item(f"總共 {sum(c.values())}", g(str(sum(c.values()))), g(*TOTAL), line=True))
    return out


# ---- 限定範圍的找檔案與計數 ----

def cnt_rmf_publishers(root):
    c = _calls_by_file(root, "fih_rmf_system/fih_rmf_system", "create_publisher")
    pkg = _grep_all(root, "fih_rmf_system", "create_publisher(")
    return {"answer": f"{len(c)} 個檔案、共 {sum(c.values())} 次（整個套件的文字搜尋是 {pkg[0]} 個檔案、{pkg[1]} 次）",
            "items": _counts(c),
            "forbid": [item(f"答成整個套件的總數 {n}", g(str(n)), g(*TOTAL), line=True) for n in sorted({pkg[1], pkg[2]})]}


def _grep_all(root, scope, text):
    """scope 底下所有文字檔：（含 text 的檔案數, 出現次數, 只算 .py 的次數）。"""
    files = hits = py = 0
    for dp, dns, fns in os.walk(os.path.join(root, scope)):
        for fn in fns:
            try:
                with open(os.path.join(dp, fn), encoding="utf-8") as f:
                    n = f.read().count(text)
            except (UnicodeDecodeError, OSError):
                continue
            if n:
                files, hits = files + 1, hits + n
                py += n if fn.endswith(".py") else 0
    return files, hits, py


def cnt_sw_clients(root):
    c = _calls_by_file(root, "amr_base_sw/amr_base_sw", "create_client")
    pkg = _grep_all(root, "amr_base_sw", "create_client(")
    return {"answer": f"{len(c)} 個檔案、共 {sum(c.values())} 個（整個套件的文字搜尋是 {pkg[0]} 個檔案、{pkg[1]} 次）",
            "items": _counts(c),
            "forbid": [item(f"答成整個套件的總數 {n}", g(str(n)), g(*TOTAL), line=True) for n in sorted({pkg[1], pkg[2]})]}


def cnt_hw_params(root):
    c = _calls_by_file(root, "amr_base_hw", "declare_parameter")
    return {"answer": f"{len(c)} 個檔案、共 {sum(c.values())} 個", "items": _counts(c), "forbid": []}


def cnt_rmf_tests(root):
    files, funcs = 0, 0
    for rel, tree, src in _py(root, "fih_rmf_system/test"):
        if os.path.basename(rel).startswith("test_"):
            files += 1
            n = sum(1 for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name.startswith("test"))
            assert n == len(re.findall(r"^\s*(?:async\s+)?def\s+test", src, re.M)), rel
            funcs += n
    return {"answer": f"{files} 個測試檔、{funcs} 個測試函式",
            "items": [item(f"{files} 個測試檔", g(str(files))), item(f"{funcs} 個測試函式", g(str(funcs)))], "forbid": []}


def cnt_sw_specs(root):
    d = "amr_base_sw/docs/specs/nodes"
    specs = sorted(f for f in os.listdir(os.path.join(root, d)) if f.endswith(".md"))
    sizes = sorted(((_read(root, f"{d}/{f}").count("\n"), f) for f in specs), reverse=True)
    items = [item(f"{len(specs)} 份", g(str(len(specs))))]
    for n, f in sizes[:2]:
        text = _read(root, f"{d}/{f}")
        alts = sorted({str(n), str(len(text.splitlines()))})           # wc -l 與編輯器的行數（最後一行沒有換行時差 1）
        items.append(item(f"{f}：{n} 行", g(f), g(*alts), line=True))
    return {"answer": f"{len(specs)} 份；最長的是 {sizes[0][1]}（{sizes[0][0]} 行）、{sizes[1][1]}（{sizes[1][0]} 行）",
            "items": items, "forbid": []}


def _node_classes(root, scope):
    found = []
    for rel, tree, src in _py(root, scope):
        cls = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and any(ast.unparse(b) in ("Node", "rclpy.node.Node") for b in n.bases)]
        grep = re.findall(r"^\s*class\s+\w+\s*\((?:[^()]*,\s*)?(?:rclpy\.node\.)?Node\s*(?:,[^()]*)?\)\s*:", src, re.M)
        assert len(cls) == len(grep), rel
        found += [(rel, n.name) for n in cls]
    return found


def cnt_sw_nodes(root):
    found = _node_classes(root, "amr_base_sw/amr_base_sw")
    whole = len(_node_classes(root, "amr_base_sw"))
    files = [p for p, _ in found]       # 有兩個檔案都定義了同名的類別（RecoveryArbiterNode），所以連檔案一起核對
    return {"answer": f"{len(found)} 個類別（{len({p for p, _ in found})} 個檔案；整個套件是 {whole} 個）",
            "items": [item(f"總共 {len(found)}", g(str(len(found))), g(*TOTAL, "個類別"), line=True)]
            + [item(f"{n}（{_short(p, files)}）", g(n), g(_short(p, files)), line=True) for p, n in found],
            "forbid": [item(f"答成整個套件的數量 {whole}", g(str(whole)), g(*TOTAL, "個類別"), line=True)]}


# ---- 讀長文件回答 ----

def doc_task_confirm(root):
    rel = "amr_base_sw/docs/specs/nodes/task_agent.md"
    s8, ids8 = _row(root, rel, "TSK-S08", "WAITING_CONFIRM", "不同 task_id 的 confirm", "不變：繼續等")
    s6, ids6 = _row(root, rel, "TSK-S06", "WAITING_CONFIRM", "同一筆的 authorize 又來", "重發 `yes`", "不重新計時")
    return {"answer": f"TSK-S08（第 {s8} 行）：狀態不變，繼續等；TSK-S06（第 {s6} 行）：狀態不變，重發 yes，不重新計時",
            "items": [item("TSK-S08：不變、繼續等", g(*ids8), g("繼續等", "持續等", "維持", "不變", "保持"), near=300),
                      item("TSK-S06：重發 yes", g(*ids6), g("yes"), near=300),
                      item("TSK-S06：不重新計時", g(*ids6), g("不重新計時", f"re:不{NEG}(計時|起算)", f"re:計時{NEG}(不變|照舊)"), near=300)],
            "forbid": []}


def doc_nav_stop(root):
    rel = "amr_base_sw/docs/specs/nodes/LocalNavNode.md"
    n, ids = _row(root, rel, "LNV-S26", "任何狀態", "`cmd_stop`", "不回報", "| IDLE |")
    return {"answer": f"LNV-S26（第 {n} 行）：回到 IDLE，不回報",
            "items": [item("LNV-S26：IDLE", g(*ids), g("IDLE"), near=300),
                      item("不回報", g(*ids), g("不回報", f"re:不{NEG}回報", f"re:(沒有|無){NEG}回報"), near=300)],
            "forbid": []}


def doc_gate_startup(root):
    rel = "amr_base_sw/docs/specs/nodes/safety_motion_controller.md"
    n, ids = _row(root, rel, "GATE-S06", "require_safety_command=true", "保護停車（`NO_SAFETY_COMMAND_YET`）", "第一筆輸出就是 0")
    return {"answer": f"GATE-S06（第 {n} 行）：保護停車（NO_SAFETY_COMMAND_YET），第一筆輸出就是 0",
            "items": [item("GATE-S06：保護停車", g(*ids), g("NO_SAFETY_COMMAND_YET", "保護停車", "re:protective.?stop"), near=300),
                      item("第一筆輸出是 0", g("輸出", "送出", "發出", "發布", "output"), g("0", "零"), line=True)],
            "forbid": []}


def doc_sched_iter(root):
    rel = "fih_rmf_system/docs/specs/nodes/scheduler.md"
    n, ids = _row(root, rel, "SCH-P06", "`scheduler.max_delay_threshold_iter`", "2000", "疊代次數上限")
    return {"answer": f"SCH-P06（第 {n} 行）：疊代次數的上限（名稱裡的 delay 和用途無關），預設 2000",
            "items": [item("SCH-P06：2000", g(*ids), g("2000"), near=300),
                      item("是疊代次數的上限", g("疊代", "迭代", "iteration", "循環次數", "重複次數"))],
            "forbid": []}


def doc_pred_map(root):
    rel = "fih_rmf_system/docs/specs/nodes/predictor.md"
    n, ids = _row(root, rel, "PRD-O07", "地圖只在啟動時讀一次，失敗時照常執行", "ERROR", "剔光")
    return {"answer": f"PRD-O07（第 {n} 行）：地圖只在啟動時讀一次；失敗時照常執行，只記一筆 ERROR 事件，stations 是空的；"
                      "之後每台的序列都被剔光，每個站點記一次 WARN",
            "items": [item("PRD-O07：只記 ERROR", g(*ids), g("ERROR", "re:error"), near=300),
                      item("照常執行", g("照常執行", f"re:(照常|照樣|仍|繼續|還是|一樣){NEG}(執行|運作|成功|跑|啟動|configure)", f"re:不{NEG}(停止|中止|停下)")),
                      item("序列被剔光", g("剔光", "re:(剔|移除|清空|丟掉|刪除|濾掉|過濾|丟棄|去掉|拿掉|捨棄)"))],
            "forbid": []}


def doc_dock_align(root):
    rel = "amr_base_sw/docs/specs/nodes/LocalDockNode.md"
    n, ids = _row(root, rel, "LDK-S15", "`PRE_DOCK_ALIGN`", "朝向對了但橫向超差", "`PRE_DOCK_NAV`")
    return {"answer": f"LDK-S15（第 {n} 行）：轉到 PRE_DOCK_NAV",
            "items": [item("LDK-S15：PRE_DOCK_NAV", g(*ids), g("PRE_DOCK_NAV"), near=300)], "forbid": []}


# ---- Python 的定義與呼叫 ----

def _py_question(root, scope, name, with_class):
    (rel, line, cls), calls = _def_and_callers(root, scope, name)
    files = [rel] + [p for p, _ in calls]
    # 類別名稱跟檔名一樣時（PathCollisionChecker.py 的 PathCollisionChecker），寫出檔名就有類別名稱，不另外算一則
    named = with_class and cls and cls != os.path.splitext(os.path.basename(rel))[0]
    items = ([item(f"類別 {cls}", g(cls))] if named else []) + [_file_line(rel, line, files)]
    items += [_file_line(p, ln, files) for p, ln in calls]
    where = ", ".join(f"{_short(p, files)}:{ln}" for p, ln in calls)
    return {"answer": f"定義：{(cls + '.') if cls else ''}{name}（{_short(rel, files)}:{line}）；呼叫：{where}", "items": items, "forbid": []}


def py_solve_conflicts(root):
    return _py_question(root, "fih_rmf_system/fih_rmf_system", "solve_conflicts", True)


def py_fleet_msg(root):
    return _py_question(root, "fih_rmf_system/fih_rmf_system", "fleet_states_to_msg", False)


def py_pre_dock(root):
    return _py_question(root, "amr_base_sw/amr_base_sw", "compute_pre_dock_pose", False)


def py_speed_limit(root):
    return _py_question(root, "amr_base_sw/amr_base_sw", "apply_speed_limit", False)


def py_encoder(root):
    return _py_question(root, "amr_base_hw", "update_from_encoder_counts_s32", True)


def py_check_path(root):
    return _py_question(root, "amr_base_sw/amr_base_sw", "check_path", True)


# ---- C++ ----

def cpp_rf2o_params(root):
    rel = "amr_base_hw/rf2o_laser_odometry/src/CLaserOdometry2DNode.cpp"
    params = re.findall(r'declare_parameter<\s*([\w:]+)\s*>\(\s*"(\w+)"\s*,\s*"?([^")]*)"?\s*\)', _read(root, rel))
    assert len(params) == 7, params
    items = []
    for typ, name, default in params:
        alts = [default]
        if typ == "double" and default.endswith(".0"):
            alts.append(default[:-2])
        items.append(item(f"{name} = {default}", g(name), g(*alts), line=True))
    return {"answer": "、".join(f"{n}={d}" for _, n, d in params) + f"（{os.path.basename(rel)}）", "items": items, "forbid": []}


def cpp_sick_ports(root):
    rel = "amr_base_hw/sick_scan_xd/driver/src/sick_scansegment_xd/config.cpp"
    got = {}
    for key, pat in (("udp_port", r"^\s*udp_port\s*=\s*(\d+);"), ("imu_udp_port", r"^\s*imu_udp_port\s*=\s*(\d+);"),
                     ("sopas_tcp_port", r'^\s*sopas_tcp_port\s*=\s*"(\d+)";')):
        n = _line_of(root, rel, pat)
        got[key] = (re.search(pat, _lines(root, rel)[n - 1]).group(1), n)
    return {"answer": f"UDP {got['udp_port'][0]}、IMU 的 UDP {got['imu_udp_port'][0]}、SOPAS 的 TCP {got['sopas_tcp_port'][0]}"
                      f"（config.cpp 第 {got['udp_port'][1]}、{got['imu_udp_port'][1]}、{got['sopas_tcp_port'][1]} 行）",
            "items": [item("config.cpp", g("config.cpp")),
                      item(f"UDP port {got['udp_port'][0]}", g(got["udp_port"][0]), g("udp", "re:udp"), line=True),
                      item(f"IMU 的 UDP port {got['imu_udp_port'][0]}", g(got["imu_udp_port"][0]), g("imu", "re:imu"), line=True),
                      item(f"SOPAS 的 TCP port {got['sopas_tcp_port'][0]}", g(got["sopas_tcp_port"][0]), g("sopas", "re:sopas|tcp"), line=True)],
            "forbid": []}


def cpp_laserscan_pub(root):
    rel = "amr_base_hw/sick_scan_xd/driver/src/sick_scansegment_xd/ros_msgpack_publisher.cpp"
    n = _line_of(root, rel, r"^\S.*\bRosMsgpackPublisher::publishLaserScanMsg\s*\(")
    return {"answer": f"publishLaserScanMsg（ros_msgpack_publisher.cpp:{n}）",
            "items": [item("publishLaserScanMsg", g("publishLaserScanMsg")), _file_line(rel, n)], "forbid": []}


def cpp_sick_services(root):
    base = "amr_base_hw/sick_scan_xd"
    hdr = [p for p in _all_files(root, base, (".h", ".hpp")) if re.search(r"^\s*class\s+SickScanServices\b[^;]*$", _read(root, p), re.M)]
    impl = [p for p in _all_files(root, base, (".cpp",)) if re.search(r"\bSickScanServices::SickScanServices\s*\(", _read(root, p))]
    assert len(hdr) == 1 and len(impl) == 1, (hdr, impl)
    return {"answer": f"宣告：{os.path.relpath(hdr[0], base)}；實作：{os.path.relpath(impl[0], base)}",
            "items": [item(os.path.basename(hdr[0]), g(os.path.basename(hdr[0]))), item(os.path.basename(impl[0]), g(os.path.basename(impl[0])))],
            "forbid": []}


def _all_files(root, scope, exts):
    for dp, dns, fns in os.walk(os.path.join(root, scope)):
        for fn in fns:
            if fn.endswith(exts):
                yield os.path.relpath(os.path.join(dp, fn), root)


def cpp_laser_qos(root):
    rel = "amr_base_hw/rf2o_laser_odometry/src/CLaserOdometry2DNode.cpp"
    n = _line_of(root, rel, r"create_subscription<sensor_msgs::msg::LaserScan>")
    line = _lines(root, rel)[n - 1]
    assert "KeepLast(1)" in line and "best_effort()" in line and "durability_volatile()" in line, line
    return {"answer": f"KeepLast(1)、best_effort、durability_volatile（{os.path.basename(rel)}:{n}）",
            "items": [_file_line(rel, n), item("保留 1 筆", g("KeepLast", "keep last", "keep_last", "保留", "depth", "深度"), g("1"), line=True),
                      item("best effort", g("best_effort", "best effort", "besteffort", "best-effort")),
                      item("volatile", g("volatile", "durability_volatile"))],
            "forbid": []}


def cpp_compact_parser(root):
    rel = "amr_base_hw/sick_scan_xd/include/sick_scansegment_xd/compact_parser.h"
    n = _line_of(root, rel, r"^\s*class\s+CompactDataParser\b")
    return {"answer": f"CompactDataParser（compact_parser.h:{n}）",
            "items": [item("CompactDataParser", g("CompactDataParser")), item("compact_parser.h", g("compact_parser.h"))], "forbid": []}


# ---- 跨檔案的調查 ----

def cross_rf2o_runtime(root):
    code = "amr_base_hw/rf2o_laser_odometry/src/CLaserOdometry2DNode.cpp"
    launch = "amr_base_hw/rf2o_laser_odometry/launch/rf2o_laser_odometry.launch.py"
    bring = "amr_base_hw/hw_bringup/launch/hw_bringup.launch.py"
    ekf = "amr_base_hw/hw_bringup/config/ekf.yaml"
    _line_of(root, code, r'declare_parameter<std::string>\("odom_topic", "/odom_rf2o"\)')
    _line_of(root, code, r'declare_parameter<double>\("freq", 10.0\)')
    t = _line_of(root, launch, r"'odom_topic'\s*:\s*'/rf2o_odom'")
    _line_of(root, launch, r"'freq'\s*:\s*20.0")
    _line_of(root, launch, r"'publish_tf'\s*:\s*False")
    _line_of(root, bring, r"'rf2o_laser_odometry.launch.py'")
    e = _line_of(root, ekf, r"^\s*odom1:\s*/rf2o_odom\s*$")
    _line_of(root, bring, r"executable='ekf_node'")
    return {"answer": f"/rf2o_odom、20 Hz、不發 TF（rf2o 的 launch 第 {t} 行起覆寫了程式的預設 /odom_rf2o、10 Hz、發 TF）；"
                      f"robot_localization 的 EKF 用它（ekf.yaml:{e} 的 odom1）",
            "items": [item("/rf2o_odom", g("/rf2o_odom")), item("20 Hz", g("20", "20.0"), g("hz", "頻率", "freq"), line=True),
                      item("不發 TF", g("tf", "publish_tf"), g("false", "不發", "不會發", "不發布", "不廣播", "關閉", "沒有發", "不會廣播", "不會發布"), line=True),
                      item("EKF 用它", g("ekf", "re:ekf", "robot_localization"))],
            "forbid": []}


def cross_scan_chain(root):
    bring = "amr_base_hw/hw_bringup/launch/hw_bringup.launch.py"
    for pat in (r"'publish_laserscan_fullframe_topic':\s*'/sick/front/lidar'", r"'publish_laserscan_fullframe_topic':\s*'/sick/back/lidar'",
                r"executable='laser_scan_merger'", r"'output_topic':\s*'/scan_merged'", r"\('scan',\s*'/scan_merged'\)",
                r"\('scan_filtered',\s*'/scan'\)", r"executable='scan_to_scan_filter_chain'"):
        _line_of(root, bring, pat)
    _line_of(root, "amr_base_hw/rf2o_laser_odometry/launch/rf2o_laser_odometry.launch.py", r"'laser_scan_topic'\s*:\s*'/scan'")
    return {"answer": "兩台 picoScan（sick_scan_xd）發 /sick/front/lidar、/sick/back/lidar → laser_scan_merger 合成 /scan_merged → "
                      "laser_filters 的 scan_to_scan_filter_chain 濾完發 /scan → rf2o 訂閱 /scan",
            "items": [item("/sick/front/lidar", g("/sick/front/lidar")), item("/sick/back/lidar", g("/sick/back/lidar")),
                      item("laser_scan_merger", g("laser_scan_merger")), item("/scan_merged", g("/scan_merged")),
                      item("laser_filters", g("scan_to_scan_filter_chain", "laser_filters", "laser_filter"))],
            "forbid": []}


def cross_speed_limit(root):
    launch = "amr_base_sw/launch/start_sim_and_spawn_Base.launch.py"
    node = "amr_base_sw/amr_base_sw/safety_control/safety_motion_controller.py"
    _line_of(root, launch, r"^SPEED_LIMIT_NAV = '/speed_limit_nav'")
    _line_of(root, launch, r"^SPEED_LIMIT_DOCK = '/speed_limit_dock'")
    _line_of(root, launch, r"^SPEED_LIMIT_OUT = '/speed_limit'")
    _line_of(root, launch, r"remappings=\[\('/speed_limit', SPEED_LIMIT_NAV\)\]")
    _line_of(root, launch, r"'local_nav_speed_limit_topic': SPEED_LIMIT_NAV")
    _line_of(root, launch, r"'speed_limit_output_topic': SPEED_LIMIT_OUT")
    s = _line_of(root, node, r"^LIMIT_SOURCE_PARAMS = \(\(RMF_LIMIT_SOURCE, 'rmf_speed_limit_topic'")
    return {"answer": f"LocalNavNode 的 /speed_limit 被 remap 成 /speed_limit_nav → safety_motion_controller 合併 rmf、local_nav、"
                      f"local_dock（/speed_limit_dock）三個來源（safety_motion_controller.py:{s}）→ 輸出到 /speed_limit",
            "items": [item("/speed_limit_nav", g("/speed_limit_nav")), item("safety_motion_controller", g("safety_motion_controller")),
                      item("dock 的限速來源", g("/speed_limit_dock", "local_dock", "re:local.?dock")), item("RMF 的限速來源", g("rmf", "re:rmf", "調度")),
                      item("輸出到 /speed_limit", g("/speed_limit"), g("輸出", "output", "最後", "合併後", "發到", "送到", "發布到"), line=True)],
            "forbid": []}


def cross_sched_tuning(root):
    yml = "fih_rmf_system/config/tuning.yaml"
    n = _line_of(root, yml, r"^\s*l2_trigger_delay_ms:\s*5500\b")
    d = _line_of(root, "fih_rmf_system/fih_rmf_system/scheduler/spatio_temporal_scheduler.py", r"^\s*l2_trigger_delay_ms:\s*int\s*=\s*5500\b")
    _line_of(root, "fih_rmf_system/fih_rmf_system/scheduler/scheduler_node.py", r"config\.get\(f'scheduler\.\{key\}'")
    _line_of(root, "fih_rmf_system/fih_rmf_system/scheduler/scheduler_node.py", r"^from fih_rmf_system import config_loader as config")
    return {"answer": f"config/tuning.yaml:{n} 寫 5500；scheduler_node.py 經 config_loader 讀 scheduler.l2_trigger_delay_ms，"
                      f"沒寫時用 SchedulerParams 的預設 5500（spatio_temporal_scheduler.py:{d}）",
            "items": [item("tuning.yaml", g("tuning.yaml")), item("5500", g("5500")),
                      item("config_loader 讀", g("config_loader", "_cfg", "config.get")),
                      _file_line("fih_rmf_system/fih_rmf_system/scheduler/spatio_temporal_scheduler.py", d)],
            "forbid": []}


def cross_imu(root):
    bring = "amr_base_hw/hw_bringup/launch/hw_bringup.launch.py"
    ekf = "amr_base_hw/hw_bringup/config/ekf.yaml"
    lines = _lines(root, bring)
    i = next(k for k, ln in enumerate(lines) if "DeclareLaunchArgument(" in ln and "use_tdk_imu" in ln + lines[k + 1])
    assert "default_value='true'" in "".join(lines[i:i + 4]), lines[i:i + 4]
    _line_of(root, bring, r"condition=IfCondition\(use_tdk_imu\)")
    _line_of(root, bring, r"remappings=\[\('/tdk/imu', '/imu_data'\)\]")
    e = _line_of(root, ekf, r"^\s*imu0:\s*/imu_data\s*$")
    return {"answer": f"預設用 tdk_ros2_imu（use_tdk_imu 預設 true）；/tdk/imu remap 成 /imu_data；robot_localization 的 EKF 用它（ekf.yaml:{e} 的 imu0）",
            "items": [item("tdk_ros2_imu", g("tdk_ros2_imu", "re:tdk")), item("/imu_data", g("/imu_data")),
                      item("EKF 用它", g("ekf", "re:ekf", "robot_localization"))],
            "forbid": []}


def cross_odom_source(root):
    bring = "amr_base_hw/hw_bringup/launch/hw_bringup.launch.py"
    ekf = "amr_base_hw/hw_bringup/config/ekf.yaml"
    _line_of(root, bring, r"\('odometry/filtered', '/odom'\)")
    _line_of(root, bring, r"executable='odom_tf_broadcaster'")
    _line_of(root, bring, r"condition=UnlessCondition\(use_robot_localization\)")
    _line_of(root, bring, r"'input_odom_topic': '/wheel_odom'")
    srcs = {k: _line_of(root, ekf, rf"^\s*{k}:\s*/\w+\s*$") for k in ("odom0", "odom1", "imu0")}
    topics = {k: _lines(root, ekf)[n - 1].split(":")[1].strip() for k, n in srcs.items()}
    assert topics == {"odom0": "/wheel_odom", "odom1": "/rf2o_odom", "imu0": "/imu_data"}, topics
    return {"answer": "預設是 robot_localization 的 ekf_node（odometry/filtered remap 成 /odom），融合 /wheel_odom、/rf2o_odom、/imu_data；"
                      "use_robot_localization 關掉時改由 my_robot_description 的 odom_tf_broadcaster 把 /wheel_odom 轉發成 /odom",
            "items": [item("EKF 發布", g("ekf", "re:ekf", "robot_localization")), item("/wheel_odom", g("/wheel_odom")), item("/rf2o_odom", g("/rf2o_odom")),
                      item("/imu_data", g("/imu_data")), item("關掉時 odom_tf_broadcaster", g("odom_tf_broadcaster", "wheel_odom_to_odom"))],
            "forbid": []}


# ---- 題目 ----

def Q(qid, kind, qset, package, question, compute):
    return {"id": qid, "kind": kind, "set": qset, "package": package, "question": question, "compute": compute}


QUESTIONS = [
    Q("cnt_rmf_publishers", "count", "main", "fih_rmf_system",
      "fih_rmf_system 的程式（fih_rmf_system/fih_rmf_system/，不含 test、docs）裡，哪些 Python 檔呼叫了 create_publisher？各幾次、總共幾次？",
      cnt_rmf_publishers),
    Q("cnt_sw_clients", "count", "main", "amr_base_sw",
      "amr_base_sw 的程式（amr_base_sw/amr_base_sw/，不含 test、tool）裡，哪些檔案建立了 service client（create_client）？各幾個、總共幾個？",
      cnt_sw_clients),
    Q("cnt_hw_params", "count", "main", "amr_base_hw",
      "amr_base_hw 裡哪些 Python 檔宣告了 ROS 參數（declare_parameter）？各幾個、總共幾個？", cnt_hw_params),
    Q("cnt_rmf_tests", "count", "main", "fih_rmf_system",
      "fih_rmf_system 的 test/ 底下有幾個測試檔（檔名 test_ 開頭的 .py）？這些檔案裡總共有幾個測試函式（名稱 test 開頭的 def）？", cnt_rmf_tests),
    Q("cnt_sw_specs", "count", "main", "amr_base_sw",
      "amr_base_sw 的 docs/specs/nodes/ 底下有幾份規格書（.md）？最長的兩份是哪兩份、各幾行？", cnt_sw_specs),
    Q("cnt_sw_nodes", "count", "holdout", "amr_base_sw",
      "amr_base_sw 的程式（amr_base_sw/amr_base_sw/，不含 test、tool）裡，有幾個類別直接繼承 rclpy 的 Node？列出類別名稱與所在的檔案。", cnt_sw_nodes),

    Q("doc_task_confirm", "doc", "main", "amr_base_sw",
      "照 amr_base_sw 的 task_agent 規格書（docs/specs/nodes/task_agent.md）：WAITING_CONFIRM 時收到不同 task_id 的 confirm 會怎樣？"
      "同一筆的 authorize 又來呢？各引用規格書的編號。", doc_task_confirm),
    Q("doc_nav_stop", "doc", "main", "amr_base_sw",
      "照 amr_base_sw 的 LocalNavNode 規格書：LocalNavNode 在任何狀態收到 cmd_stop 會轉到哪個狀態？會不會回報？引用規格書的編號。", doc_nav_stop),
    Q("doc_gate_startup", "doc", "main", "amr_base_sw",
      "照 amr_base_sw 的 safety_motion_controller 規格書：require_safety_command 是 true 時，節點剛啟動、還沒收到安全指令，"
      "會進入什麼狀態、第一筆輸出是什麼？引用規格書的編號。", doc_gate_startup),
    Q("doc_sched_iter", "doc", "main", "fih_rmf_system",
      "照 fih_rmf_system 的 scheduler 規格書：scheduler.max_delay_threshold_iter 實際上是什麼的上限？預設多少？引用規格書的編號。", doc_sched_iter),
    Q("doc_pred_map", "doc", "main", "fih_rmf_system",
      "照 fih_rmf_system 的 predictor 規格書：predictor 啟動時讀地圖失敗會怎樣？之後收到的序列怎麼處理？引用規格書的編號。", doc_pred_map),
    Q("doc_dock_align", "doc", "holdout", "amr_base_sw",
      "照 amr_base_sw 的 LocalDockNode 規格書：PRE_DOCK_ALIGN 狀態下朝向對了但橫向超差，會轉到哪個狀態？引用規格書的編號。", doc_dock_align),

    Q("py_solve_conflicts", "python", "main", "fih_rmf_system",
      "fih_rmf_system 的程式裡，solve_conflicts 定義在哪個類別、哪個檔案的第幾行？哪些地方呼叫它（檔案與行號）？", py_solve_conflicts),
    Q("py_fleet_msg", "python", "main", "fih_rmf_system",
      "fih_rmf_system 的程式裡，fleet_states_to_msg 定義在哪個檔案的第幾行？哪些地方呼叫它（檔案與行號）？", py_fleet_msg),
    Q("py_pre_dock", "python", "main", "amr_base_sw",
      "amr_base_sw 的程式（amr_base_sw/amr_base_sw/）裡，compute_pre_dock_pose 定義在哪個檔案的第幾行？哪些地方呼叫它（檔案與行號）？", py_pre_dock),
    Q("py_speed_limit", "python", "main", "amr_base_sw",
      "amr_base_sw 的程式（amr_base_sw/amr_base_sw/）裡，apply_speed_limit 定義在哪個檔案的第幾行？哪些地方呼叫它（檔案與行號，全部列出）？",
      py_speed_limit),
    Q("py_encoder", "python", "main", "amr_base_hw",
      "amr_base_hw 裡，update_from_encoder_counts_s32 是哪個類別的方法、定義在哪個檔案的第幾行？哪些地方呼叫它（檔案與行號）？", py_encoder),
    Q("py_check_path", "python", "holdout", "amr_base_sw",
      "amr_base_sw 的程式（amr_base_sw/amr_base_sw/）裡，check_path 是哪個類別的方法、定義在哪個檔案的第幾行？哪些地方呼叫它（檔案與行號，全部列出）？",
      py_check_path),

    Q("cpp_rf2o_params", "cpp", "main", "amr_base_hw",
      "amr_base_hw 的 rf2o_laser_odometry（C++）節點宣告了哪些 ROS 參數？各自的預設值是什麼？", cpp_rf2o_params),
    Q("cpp_sick_ports", "cpp", "main", "amr_base_hw",
      "amr_base_hw 的 sick_scan_xd 裡，scansegment_xd 的設定（Config）預設的 UDP port、IMU 的 UDP port、SOPAS 的 TCP port 各是多少？在哪個檔案設定？",
      cpp_sick_ports),
    Q("cpp_laserscan_pub", "cpp", "main", "amr_base_hw",
      "amr_base_hw 的 sick_scan_xd 裡，RosMsgpackPublisher 類別的哪個成員函式負責發布 LaserScan 訊息？定義在哪個檔案的第幾行？", cpp_laserscan_pub),
    Q("cpp_sick_services", "cpp", "main", "amr_base_hw",
      "amr_base_hw 的 sick_scan_xd 裡，SickScanServices 類別宣告在哪個標頭檔？成員函式實作在哪個 .cpp？", cpp_sick_services),
    Q("cpp_laser_qos", "cpp", "main", "amr_base_hw",
      "amr_base_hw 的 rf2o_laser_odometry 節點用什麼 QoS 訂閱雷射掃描（保留幾筆、reliability、durability）？在哪個檔案的第幾行？", cpp_laser_qos),
    Q("cpp_compact_parser", "cpp", "holdout", "amr_base_hw",
      "amr_base_hw 的 sick_scan_xd 裡，compact 格式的掃描資料由哪個類別解析？這個類別宣告在哪個標頭檔？", cpp_compact_parser),

    Q("cross_rf2o_runtime", "cross", "main", "amr_base_hw",
      "照 amr_base_hw 裡的程式與設定檔回答：實機用 hw_bringup 啟動時，rf2o 的里程計發布到哪個 topic、頻率多少、會不會發 TF？誰用這個里程計？", cross_rf2o_runtime),
    Q("cross_scan_chain", "cross", "main", "amr_base_hw",
      "照 amr_base_hw 裡的程式與設定檔回答：實機用 hw_bringup 啟動時，rf2o 訂閱的 /scan 是怎麼來的？從雷射開始經過哪些節點、各段的 topic 叫什麼？", cross_scan_chain),
    Q("cross_speed_limit", "cross", "main", "amr_base_sw",
      "模擬啟動（amr_base_sw 的 launch/start_sim_and_spawn_Base.launch.py）時，LocalNavNode 發出的限速送到哪個 topic？"
      "由哪個節點合併、它還合併了哪些限速來源？合併後輸出到哪個 topic？", cross_speed_limit),
    Q("cross_sched_tuning", "cross", "main", "fih_rmf_system",
      "fih_rmf_system 的 scheduler 用的 l2_trigger_delay_ms 從哪個設定檔讀、值是多少？由哪段程式讀？設定檔沒寫時的預設值是多少、寫在哪個檔案的第幾行？",
      cross_sched_tuning),
    Q("cross_imu", "cross", "main", "amr_base_hw",
      "照 amr_base_hw 裡的程式與設定檔回答：實機用 hw_bringup 啟動時，預設用哪一顆 IMU 的驅動？它的資料發到哪個 topic（remap 之後）？誰在用這個資料？", cross_imu),
    Q("cross_odom_source", "cross", "holdout", "amr_base_hw",
      "照 amr_base_hw 裡的程式與設定檔回答：實機用 hw_bringup 啟動時，預設由哪個節點發布 /odom？它融合了哪些輸入 topic？把 use_robot_localization 關掉時改由哪個節點發布？",
      cross_odom_source),
]


def compute_all(root):
    out = []
    for q in QUESTIONS:
        a = q["compute"](root)
        out.append({k: v for k, v in q.items() if k != "compute"} | a)
    return out


def _with_snapshot(fn):
    import snapshot
    tmp = tempfile.mkdtemp(prefix="repo_answers_")
    try:
        return fn(snapshot.extract(tmp))
    finally:
        snapshot.remove(tmp)


def load():
    with open(ANSWERS, encoding="utf-8") as f:
        return json.load(f)


def main():
    sys.path.insert(0, HERE)
    import snapshot
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    got = {"commit": snapshot.COMMIT, "digest": snapshot.DIGEST, "questions": _with_snapshot(compute_all)}
    if args.write:
        with open(ANSWERS, "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"[PASS] {len(got['questions'])} 題 → {ANSWERS}")
    elif args.check:
        same = got == load()
        print("[PASS] answers.json 跟快照算出來的一樣" if same else "[ERROR] answers.json 跟快照算出來的不一樣（python3 evals/repo/questions.py --write）")
        sys.exit(0 if same else 1)
    else:
        for q in got["questions"]:
            print(f"{q['id']}（{q['set']}）：{q['answer']}")


if __name__ == "__main__":
    main()
