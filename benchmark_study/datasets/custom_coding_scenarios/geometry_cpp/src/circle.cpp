#include "geometry/circle.hpp"

#include <cmath>
#include <stdexcept>

namespace geometry {

Circle::Circle(double radius) : radius_(radius) {
    if (radius <= 0) {
        throw std::invalid_argument("radius must be positive");
    }
}

std::string Circle::name() const { return "circle"; }

double Circle::area() const { return M_PI * radius_ * radius_; }

}  // namespace geometry
