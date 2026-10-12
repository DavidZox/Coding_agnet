# ringbuf

固定容量的環形緩衝區（C11）與移動平均命令列工具，測試用 GoogleTest（C++）。

- `include/ringbuf.h`、`src/ringbuf.c`：環形緩衝區（滿了再放會蓋掉最舊的）
- `src/main.c`：`movavg <N>`，從標準輸入一行讀一個數字，每讀一個就印出最近 N 個的平均（兩位小數）
- `tests/`：GoogleTest 測試

建置與測試：`make`、`make test`
