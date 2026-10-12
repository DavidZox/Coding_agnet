#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <cmath>

class Circle : public Shape {
private:
    double radius;

public:
    Circle() : radius(0) {
        std::cout << "Circle()" << std::endl;
    }
    Circle(double _r) : radius(_r) {
        std::cout << "Circle(" << radius << ")" << std::endl;
    }
    ~Circle() {
        std::cout << "~Circle()" << std::endl;
    }
    double calcArea() override {
        return M_PI * radius * radius;
    }
};

#endif // CIRCLE_HPP
