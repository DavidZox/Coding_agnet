#include "geometry/rectangle.hpp"

#include <stdexcept>

namespace geometry {

Rectangle::Rectangle(double width, double height) : width_(width), height_(height) {
    if (width <= 0 || height <= 0) {
        throw std::invalid_argument("width and height must be positive");
    }
}

std::string Rectangle::name() const { return "rect"; }

double Rectangle::area() const { return width_ * height_; }

}  // namespace geometry
