**E6**

| 情境 | guards-on：通過 | guards-off：通過 | guards-on：主模型呼叫 | guards-off：主模型呼叫 |
|---|---|---|---|---|
| robust_claim | 1/3（tools_any 1/3、no_step_limit 3/3） | 2/3（tools_any 2/3、no_step_limit 3/3） | 8.7 | 11.0 |
| robust_quoting | 3/3（reply_any 3/3、tools_any 3/3） | 2/3（reply_any 2/3、tools_any 3/3） | 3.0 | 4.7 |
| robust_stuck_error | 3/3（reply_any 3/3、no_step_limit 3/3） | 3/3（reply_any 3/3、no_step_limit 3/3） | 6.3 | 7.3 |
| robust_typo_dir | 3/3（reply_any 3/3、args_any 3/3） | 3/3（reply_any 3/3、args_any 3/3） | 4.3 | 7.0 |
| robust_typo_file | 1/3（reply_any 1/3、tools_any 1/3） | 3/3（reply_any 3/3、tools_any 3/3） | 4.0 | 7.3 |
| 合計 | **11/15**（73.3% [48.0, 89.1]） | **13/15**（86.7% [62.1, 96.3]） | 5.3 | 7.5 |

**E7**

| 情境 | v4.1 把關開啟：通過 | v4 的規則（對照）：通過 | 把關全部關閉：通過 | v4.1 把關開啟：主模型呼叫 | v4 的規則（對照）：主模型呼叫 | 把關全部關閉：主模型呼叫 |
|---|---|---|---|---|---|---|
| robust_claim | 9/10（tools_any 9/10、no_step_limit 10/10） | 5/10（tools_any 5/10、no_step_limit 10/10） | 6/10（tools_any 6/10、no_step_limit 10/10） | 11.1 | 10.3 | 10.5 |
| robust_quoting | 10/10（reply_any 10/10、tools_any 10/10） | 10/10（reply_any 10/10、tools_any 10/10） | 9/10（reply_any 9/10、tools_any 10/10） | 3.8 | 3.4 | 6.7 |
| robust_stuck_error | 10/10（reply_any 10/10、no_step_limit 10/10） | 10/10（reply_any 10/10、no_step_limit 10/10） | 10/10（reply_any 10/10、no_step_limit 10/10） | 6.6 | 6.1 | 5.9 |
| robust_typo_dir | 5/10（reply_any 6/10、args_any 8/10） | 7/10（reply_any 8/10、args_any 8/10） | 4/10（reply_any 6/10、args_any 5/10） | 4.7 | 4.6 | 6.3 |
| robust_typo_file | 5/10（reply_any 5/10、tools_any 5/10） | 5/10（reply_any 5/10、tools_any 6/10） | 8/10（reply_any 8/10、tools_any 8/10） | 5.3 | 4.7 | 6.2 |
| 合計 | **39/50**（78.0% [64.8, 87.2]） | **37/50**（74.0% [60.4, 84.1]） | **37/50**（74.0% [60.4, 84.1]） | 6.3 | 5.8 | 7.1 |
