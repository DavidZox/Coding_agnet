#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>
#include <cmath>

class Circle : public Shape {
public:
    Circle() : Shape(), radius(0) {}
    ~Circle() {
        std::cout << "~Circle()" << std::endl;
    }
    Circle(double radius) : Shape(), radius(radius) {
        std::cout << "Circle(r)" << std::endl;
    }
    double calcArea() override {
        return std::acos(-1.0) * radius * radius;
    }

private:
    double radius;
};

#endif // CIRCLE_HPP
