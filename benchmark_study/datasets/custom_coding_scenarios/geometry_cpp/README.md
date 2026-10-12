# geometry

計算幾何圖形面積的小函式庫與命令列工具（C++17、CMake、GoogleTest）。

- `include/geometry/`：`Shape`（抽象類別）、`Circle`、`Rectangle`、`registry.hpp`（從文字建立圖形、加總面積）
- `src/`：實作
- `app/main.cpp`：`geometry_cli <檔案>`，檔案每行一個圖形（`circle 半徑`、`rect 寬 高`），印出每個圖形的面積與總面積
- `tests/`：GoogleTest 測試

建置與測試：

```
cmake -S . -B build && cmake --build build && ctest --test-dir build
```
