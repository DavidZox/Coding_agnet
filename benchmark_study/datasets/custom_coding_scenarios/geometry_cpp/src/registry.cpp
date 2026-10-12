#include "geometry/registry.hpp"

#include <sstream>
#include <stdexcept>

#include "geometry/circle.hpp"
#include "geometry/rectangle.hpp"

namespace geometry {

std::unique_ptr<Shape> parse_shape(const std::string& line) {
    std::istringstream in(line);
    std::string kind;
    if (!(in >> kind)) {
        throw std::invalid_argument("empty shape line");
    }
    if (kind == "circle") {
        double r = 0;
        if (!(in >> r)) {
            throw std::invalid_argument("circle needs a radius: " + line);
        }
        return std::make_unique<Circle>(r);
    }
    if (kind == "rect") {
        double w = 0, h = 0;
        if (!(in >> w >> h)) {
            throw std::invalid_argument("rect needs width and height: " + line);
        }
        return std::make_unique<Rectangle>(w, h);
    }
    throw std::invalid_argument("unknown shape: " + kind);
}

ShapeList parse_shapes(const std::string& text) {
    ShapeList shapes;
    std::istringstream in(text);
    std::string line;
    while (std::getline(in, line)) {
        auto first = line.find_first_not_of(" \t\r");
        if (first == std::string::npos || line[first] == '#') {
            continue;
        }
        shapes.push_back(parse_shape(line));
    }
    return shapes;
}

double total_area(const ShapeList& shapes) {
    double sum = 0;
    for (std::size_t i = 0; i + 1 < shapes.size(); ++i) {
        sum += shapes[i]->area();
    }
    return sum;
}

}  // namespace geometry
