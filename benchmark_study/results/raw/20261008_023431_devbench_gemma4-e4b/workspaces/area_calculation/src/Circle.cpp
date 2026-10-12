#include "Circle.hpp"
#include <iostream>
#include <cmath>

// Default constructor
Circle::Circle() : radius(0.0) {
    std::cout << "Circle(0)" << std::endl;
}

// Parameterized constructor
Circle::Circle(double _r) : radius(_r) {
    std::cout << "Circle(" << _r << ")" << std::endl;
}

// Destructor
Circle::~Circle() {
    std::cout << "~Circle()" << std::endl;
}

// Override calcArea
double Circle::calcArea() {
    return M_PI * radius * radius;
}
