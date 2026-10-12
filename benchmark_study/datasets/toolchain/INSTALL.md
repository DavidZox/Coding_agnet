# 測試用的工具鏈（這台機器已經裝好，不需要 sudo）

| 工具 | 版本 | 裝在哪裡 | 怎麼裝（等效的指令） |
|---|---|---|---|
| pytest | 9.1.1 | `~/aiagent_venv_env/.venv` | `~/aiagent_venv_env/.venv/bin/pip install pytest cmake ninja` |
| cmake／ctest、ninja | 4.4.4、1.13 | 同上 | 同上 |
| GoogleTest | 1.14.0（`googletest-1.14.0.tar.gz`，sha256 `8ad598c7…`） | `~/.local`（`libgtest.a`、`libgtest_main.a`、標頭） | `tar xzf googletest-1.14.0.tar.gz && cmake -S googletest-1.14.0 -B build -DCMAKE_INSTALL_PREFIX=$HOME/.local && cmake --build build -j && cmake --install build` |
| SQLite | 3.53.4（`sqlite-amalgamation-3530400.zip`，sha256 `1e71ddf9…`） | `~/.local`（`libsqlite3.a`、`sqlite3.h`） | `unzip sqlite-amalgamation-3530400.zip && gcc -O2 -c sqlite-amalgamation-3530400/sqlite3.c -o sqlite3.o && ar rcs ~/.local/lib/libsqlite3.a sqlite3.o && cp sqlite-amalgamation-3530400/sqlite3*.h ~/.local/include/` |
| gcc／g++、make | 11.5（系統） | `/usr/bin` | 系統內建（沒有 `cc` 連結、沒有 clang） |

harness 執行指令時會把這些路徑加進 `PATH`、`CPATH`、`LIBRARY_PATH`、`CMAKE_PREFIX_PATH`（`skills_system/scripts/_code_common.toolchain_env`；位置可以用 `CODE_CPP_PREFIX` 改）。

其他機器（有 sudo 權限時最簡單）：

```bash
sudo apt install -y build-essential libgtest-dev libsqlite3-dev cmake
~/aiagent_venv_env/.venv/bin/pip install pytest
```

下載來源：GoogleTest https://github.com/google/googletest/archive/refs/tags/v1.14.0.tar.gz；SQLite https://sqlite.org/2026/sqlite-amalgamation-3530400.zip（2026-10-08 重新下載）。
