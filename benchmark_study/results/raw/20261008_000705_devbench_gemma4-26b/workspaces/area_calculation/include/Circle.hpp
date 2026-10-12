#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>
#include <cmath>

class Circle : public Shape {
private:
    double radius;

public:
    Circle() : Shape(), radius(0.0) {
        std::cout << "Circle(" << radius << ")" << std::endl;
    }

    Circle(double _r) : Shape(), radius(_r) {
        std::cout << "Circle(" << radius << ")" << std::endl;
    }

    ~Circle() {
        std::cout << "~Circle()" << std::endl;
    }

    double calcArea() override {
        return std::acos(-1.0) * radius * radius;
    }
};

#endif
