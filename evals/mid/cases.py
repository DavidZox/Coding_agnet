"""中階的真模型評測的標記（evals/mid/run.py；新架構 D10 第 3 步、D11「每一層的檢查等那一層做好再加」）。

題目沿用真實專案評測（evals/repo/questions.py 的 30 題，答案在 answers.json）。每一題標：
- skill：該用的複合技能（可以是幾個都算對的清單）；領域還沒有技能做得到的寫 none；只做得到一部分的兩個都算對
  （cnt_sw_specs 要每份規格書的行數，count_in_scope 只數得到份數；每個檔案的行數是待辦 4a ②）。讀文件、C++、跨檔案的 18 題 3b 改標
  doc_lookup、cpp_symbol、config_trace（C++ 節點的參數、設定的預設值、訂閱的 QoS 這三題 config_trace 也做得到：它也搜 C++ 檔，
  答的是設定的值與訂閱）；
- params：合約該抽出的參數（核對的寫法見 param_ok；沒寫的參數不核對）。路徑自己查到的（doc 的「X 規格書」）核對的是補上之後的值。
挑技能分開記模型挑的（selection）與第 2 級換技能之後的（py_usage 換成 cpp_symbol）。
最後的報告用 evals/repo/checks.py 對答案（skill 不是 none 的題目才算）。
保留組（set＝holdout）的標記只用來量，不拿保留組的結果調 prompts/mid/、複合技能或程式的核對（同真實專案評測）。
"""

PY_SW = {"any": ["amr_base_sw/amr_base_sw", "amr_base_sw"]}
PY_RMF = {"any": ["fih_rmf_system/fih_rmf_system", "fih_rmf_system"]}
HW_RF2O = {"any": ["amr_base_hw/rf2o_laser_odometry", "amr_base_hw"]}
HW_SICK = {"any": ["amr_base_hw/sick_scan_xd", "amr_base_hw"]}
SPECS_SW, SPECS_RMF = "amr_base_sw/docs/specs/nodes/", "fih_rmf_system/docs/specs/nodes/"

LABELS = {
    "cnt_rmf_publishers": {"skill": "py_usage", "params": {"name": "create_publisher", "path": PY_RMF}},
    "cnt_sw_clients": {"skill": "py_usage", "params": {"name": "create_client", "path": PY_SW}},
    "cnt_hw_params": {"skill": "py_usage", "params": {"name": "declare_parameter", "path": "amr_base_hw"}},
    "cnt_rmf_tests": {"skill": "count_in_scope", "params": {"files": "test_*.py", "path": "fih_rmf_system/test", "keyword": {"words": ["def", "test"]}}},
    "cnt_sw_specs": {"skill": ["count_in_scope", "none"], "params": {"files": "*.md", "path": "amr_base_sw/docs/specs/nodes"}},
    "cnt_sw_nodes": {"skill": ["none", "py_usage"]},
    "doc_task_confirm": {"skill": "doc_lookup", "params": {"doc": SPECS_SW + "task_agent.md"}},
    "doc_nav_stop": {"skill": "doc_lookup", "params": {"doc": SPECS_SW + "LocalNavNode.md"}},
    "doc_gate_startup": {"skill": "doc_lookup", "params": {"doc": SPECS_SW + "safety_motion_controller.md"}},
    "doc_sched_iter": {"skill": "doc_lookup", "params": {"doc": SPECS_RMF + "scheduler.md"}},
    "doc_pred_map": {"skill": "doc_lookup", "params": {"doc": SPECS_RMF + "predictor.md"}},
    "doc_dock_align": {"skill": "doc_lookup", "params": {"doc": SPECS_SW + "LocalDockNode.md"}},
    "py_solve_conflicts": {"skill": "py_usage", "params": {"name": "solve_conflicts", "path": PY_RMF}},
    "py_fleet_msg": {"skill": "py_usage", "params": {"name": "fleet_states_to_msg", "path": PY_RMF}},
    "py_pre_dock": {"skill": "py_usage", "params": {"name": "compute_pre_dock_pose", "path": PY_SW}},
    "py_speed_limit": {"skill": "py_usage", "params": {"name": "apply_speed_limit", "path": PY_SW}},
    "py_encoder": {"skill": "py_usage", "params": {"name": "update_from_encoder_counts_s32", "path": "amr_base_hw"}},
    "py_check_path": {"skill": "py_usage", "params": {"name": "check_path", "path": PY_SW}},
    "cpp_rf2o_params": {"skill": ["cpp_symbol", "config_trace"], "params": {"path": HW_RF2O}},
    "cpp_sick_ports": {"skill": ["cpp_symbol", "config_trace"], "params": {"path": HW_SICK}},
    "cpp_laserscan_pub": {"skill": "cpp_symbol", "params": {"path": HW_SICK, "names": {"has": ["RosMsgpackPublisher"]}}},
    "cpp_sick_services": {"skill": "cpp_symbol", "params": {"path": HW_SICK, "names": {"has": ["SickScanServices"]}}},
    "cpp_laser_qos": {"skill": ["cpp_symbol", "config_trace"], "params": {"path": HW_RF2O}},
    "cpp_compact_parser": {"skill": "cpp_symbol", "params": {"path": HW_SICK}},
    "cross_rf2o_runtime": {"skill": "config_trace", "params": {"path": "amr_base_hw"}},
    "cross_scan_chain": {"skill": "config_trace", "params": {"path": "amr_base_hw"}},
    "cross_speed_limit": {"skill": "config_trace"},
    "cross_sched_tuning": {"skill": "config_trace", "params": {"names": {"has": ["l2_trigger_delay_ms"]}}},
    "cross_imu": {"skill": "config_trace", "params": {"path": "amr_base_hw"}},
    "cross_odom_source": {"skill": "config_trace", "params": {"path": "amr_base_hw"}},
}


def wanted(label):
    return label["skill"] if isinstance(label["skill"], list) else [label["skill"]]


def param_ok(value, want):
    """一個參數對不對：字串＝一模一樣；{"any": [...]} 其中一個；{"endswith": s}；{"set": [...]} 名稱清單（不管順序）；
    {"has": [...]} 清單（名稱清單、搜尋的字）裡有這幾個；{"absent": true} 沒有抽；{"words": [...]} 每個字都在值裡（不分大小寫）。"""
    if isinstance(want, str):
        return value == want
    if "has" in want:
        return isinstance(value, list) and all(w in value for w in want["has"])
    if "any" in want:
        return value in want["any"]
    if "endswith" in want:
        return isinstance(value, str) and value.endswith(want["endswith"])
    if "set" in want:
        return isinstance(value, list) and set(value) == set(want["set"])
    if "absent" in want:
        return value is None
    return isinstance(value, str) and all(w.lower() in value.lower() for w in want["words"])


def layers(label, job):
    """挑技能與合約兩層：{"skill": 模型挑的對不對, "got": 模型挑的, "skill_final": 換技能之後的, "skill_final_ok": 它對不對,
    "params": 參數全對, "param_misses": [沒對的]}。合約核對最後用的技能的參數（換技能時參數照對應帶過去）。"""
    other = {"no_skill": "none", "out_of_domain": "out_of_domain"}.get(job.get("status"))
    sel = (job.get("selection") or {}).get("skill")
    got = sel if sel and sel not in ("none", "out_of_domain") and not (job.get("selection") or {}).get("rejected") else job.get("skill") or other
    final = job.get("skill") or other
    final_ok = final in wanted(label)
    misses = []
    if final_ok and final != "none":
        for name, want in (label.get("params") or {}).items():
            v = (job.get("params", {}).get(name) or {}).get("value")
            if not param_ok(v, want):
                misses.append(f"{name}：{v if v is not None else '沒有'}（要的是 {want!r}）")
    return {"skill": got in wanted(label), "got": got, "skill_final": final, "skill_final_ok": final_ok, "params": final_ok and not misses,
            "param_misses": misses}
