#pragma once

#include <string>

namespace geometry {

// 所有圖形的共同介面
class Shape {
public:
    virtual ~Shape() = default;
    virtual std::string name() const = 0;
    virtual double area() const = 0;
};

}  // namespace geometry
