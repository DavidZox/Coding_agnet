#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>
#include <cmath>

// Define M_PI if it's not defined by cmath (common issue on some compilers)
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

class Circle : public Shape {
private:
    double radius;

public:
    // Default constructor
    Circle() : Shape() {
        // Shape() constructor output is handled by Shape.cpp implementation
    }

    // Parameterized constructor
    Circle(double _r) : radius(_r), Shape() {
        std::cout << "Circle(" << _r << ")" << std::endl;
    }

    // Destructor
    ~Circle() {
        std::cout << "~Circle()" << std::endl;
        // Shape() destructor output is handled by Shape.cpp implementation
    }

    // Override calcArea
    double calcArea() const override {
        return M_PI * radius * radius;
    }
};

#endif // CIRCLE_HPP
