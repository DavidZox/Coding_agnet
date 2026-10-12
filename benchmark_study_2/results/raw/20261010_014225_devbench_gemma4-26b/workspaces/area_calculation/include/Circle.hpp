#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>

class Circle : public Shape {
private:
    double radius;

public:
    Circle() : Shape(), radius(0.0) {
        std::cout << "Circle(r)" << std::endl;
    }

    Circle(double _r) : Shape(), radius(_r) {
        std::cout << "Circle(r)" << std::endl;
    }

    ~Circle() override {
        std::cout << "~Circle()" << std::endl;
    }

    double calcArea() override {
        return 3.14159265358979323846 * radius * radius;
    }
};

#endif
