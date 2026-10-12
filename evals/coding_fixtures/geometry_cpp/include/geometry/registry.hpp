#pragma once

#include <memory>
#include <string>
#include <vector>

#include "geometry/shape.hpp"

namespace geometry {

using ShapeList = std::vector<std::unique_ptr<Shape>>;

// 一行文字 → 圖形："circle 2"、"rect 3 4"（前後空白不算）。看不懂的格式丟出 std::invalid_argument。
std::unique_ptr<Shape> parse_shape(const std::string& line);

// 每行一個圖形；空行與 # 開頭的註解行略過。
ShapeList parse_shapes(const std::string& text);

// 所有圖形面積的總和
double total_area(const ShapeList& shapes);

}  // namespace geometry
