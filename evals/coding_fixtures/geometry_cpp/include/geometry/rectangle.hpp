#pragma once

#include "geometry/shape.hpp"

namespace geometry {

class Rectangle : public Shape {
public:
    // width、height 必須大於 0，否則丟出 std::invalid_argument
    Rectangle(double width, double height);

    std::string name() const override;
    double area() const override;
    double width() const { return width_; }
    double height() const { return height_; }

private:
    double width_;
    double height_;
};

}  // namespace geometry
