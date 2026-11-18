"""中階的真模型評測的標記（evals/mid/run.py；新架構 D10 第 3 步、D11「每一層的檢查等那一層做好再加」）。

題目沿用真實專案評測（evals/repo/questions.py 的 30 題，答案在 answers.json）。每一題標：
- skill：該用的複合技能（可以是幾個都算對的清單）；第一版（3a）的領域還沒有技能做得到的寫 none（讀長文件、C++、跨檔案的調查是 3b）；
  只做得到一部分的兩個都算對（cnt_sw_specs 要每份規格書的行數，count_in_scope 只數得到份數）；
- params：合約該抽出的參數（核對的寫法見 param_ok；沒寫的參數不核對）。
最後的報告用 evals/repo/checks.py 對答案（skill 不是 none 的題目才算）。
保留組（set＝holdout）的標記只用來量，不拿保留組的結果調 prompts/mid/、複合技能或程式的核對（同真實專案評測）。
"""

PY_SW = {"any": ["amr_base_sw/amr_base_sw", "amr_base_sw"]}
PY_RMF = {"any": ["fih_rmf_system/fih_rmf_system", "fih_rmf_system"]}

LABELS = {
    "cnt_rmf_publishers": {"skill": "py_usage", "params": {"name": "create_publisher", "path": PY_RMF}},
    "cnt_sw_clients": {"skill": "py_usage", "params": {"name": "create_client", "path": PY_SW}},
    "cnt_hw_params": {"skill": "py_usage", "params": {"name": "declare_parameter", "path": "amr_base_hw"}},
    "cnt_rmf_tests": {"skill": "count_in_scope", "params": {"files": "test_*.py", "path": "fih_rmf_system/test", "keyword": {"words": ["def", "test"]}}},
    "cnt_sw_specs": {"skill": ["count_in_scope", "none"], "params": {"files": "*.md", "path": "amr_base_sw/docs/specs/nodes"}},
    "cnt_sw_nodes": {"skill": ["none", "py_usage"]},
    "doc_task_confirm": {"skill": "none"},
    "doc_nav_stop": {"skill": "none"},
    "doc_gate_startup": {"skill": "none"},
    "doc_sched_iter": {"skill": "none"},
    "doc_pred_map": {"skill": "none"},
    "doc_dock_align": {"skill": "none"},
    "py_solve_conflicts": {"skill": "py_usage", "params": {"name": "solve_conflicts", "path": PY_RMF}},
    "py_fleet_msg": {"skill": "py_usage", "params": {"name": "fleet_states_to_msg", "path": PY_RMF}},
    "py_pre_dock": {"skill": "py_usage", "params": {"name": "compute_pre_dock_pose", "path": PY_SW}},
    "py_speed_limit": {"skill": "py_usage", "params": {"name": "apply_speed_limit", "path": PY_SW}},
    "py_encoder": {"skill": "py_usage", "params": {"name": "update_from_encoder_counts_s32", "path": "amr_base_hw"}},
    "py_check_path": {"skill": "py_usage", "params": {"name": "check_path", "path": PY_SW}},
    "cpp_rf2o_params": {"skill": "none"},
    "cpp_sick_ports": {"skill": "none"},
    "cpp_laserscan_pub": {"skill": "none"},
    "cpp_sick_services": {"skill": "none"},
    "cpp_laser_qos": {"skill": "none"},
    "cpp_compact_parser": {"skill": "none"},
    "cross_rf2o_runtime": {"skill": "none"},
    "cross_scan_chain": {"skill": "none"},
    "cross_speed_limit": {"skill": "none"},
    "cross_sched_tuning": {"skill": "none"},
    "cross_imu": {"skill": "none"},
    "cross_odom_source": {"skill": "none"},
}


def wanted(label):
    return label["skill"] if isinstance(label["skill"], list) else [label["skill"]]


def param_ok(value, want):
    """一個參數對不對：字串＝一模一樣；{"any": [...]} 其中一個；{"endswith": s}；{"set": [...]} 名稱清單（不管順序）；
    {"absent": true} 沒有抽；{"words": [...]} 每個字都在值裡（不分大小寫）。"""
    if isinstance(want, str):
        return value == want
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
    """挑技能與合約兩層：{"skill": 對不對, "got": 選的, "params": 參數全對, "param_misses": [沒對的]}。"""
    got = job.get("skill") or {"no_skill": "none", "out_of_domain": "out_of_domain"}.get(job.get("status"))
    skill_ok = got in wanted(label)
    misses = []
    if skill_ok and got != "none":
        for name, want in (label.get("params") or {}).items():
            v = (job.get("params", {}).get(name) or {}).get("value")
            if not param_ok(v, want):
                misses.append(f"{name}：{v if v is not None else '沒有'}（要的是 {want!r}）")
    return {"skill": skill_ok, "got": got, "params": skill_ok and not misses, "param_misses": misses}
