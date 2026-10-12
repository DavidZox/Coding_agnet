#pragma once

#include "geometry/shape.hpp"

namespace geometry {

class Circle : public Shape {
public:
    // radius 必須大於 0，否則丟出 std::invalid_argument
    explicit Circle(double radius);

    std::string name() const override;
    double area() const override;
    double radius() const { return radius_; }

private:
    double radius_;
};

}  // namespace geometry
