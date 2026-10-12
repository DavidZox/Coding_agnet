#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>

class Circle : public Shape {
private:
    double radius;

public:
    Circle() : Shape(), radius(0.0) {}
    Circle(double _r) : Shape(), radius(_r) {
        std::cout << "Circle(" << radius << ")" << std::endl;
    }
    ~Circle() {
        std::cout << "~Circle()" << std::endl;
    }
    double calcArea() override {
        return 3.14159 * radius * radius;
    }
};

#endif // CIRCLE_HPP
