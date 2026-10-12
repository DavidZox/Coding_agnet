#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <cmath>
#include <iostream>

class Circle : public Shape {
private:
    double radius;

public:
    // Default constructor
    Circle() : Shape() {
        std::cout << "Circle()" << std::endl;
    }

    // Parameterized constructor
    Circle(double _r) : Shape() {
        radius = _r;
        std::cout << "Circle(" << _r << ")" << std::endl;
    }

    // Destructor
    ~Circle() {
        std::cout << "~Circle()" << std::endl;
    }

    // Override calcArea
    double calcArea() const override {
        return M_PI * radius * radius;
    }
};

#endif // CIRCLE_HPP
