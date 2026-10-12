#include "Circle.hpp"
#include <iostream>
#include <cmath>

// Circle Default Constructor
Circle::Circle() : radius(0.0) {
    Shape::Shape();
    std::cout << "Circle(0)" << std::endl;
}

// Circle Parameterized Constructor
Circle::Circle(double _r) : radius(_r) {
    Shape::Shape();
    std::cout << "Circle(" << _r << ")" << std::endl;
}

// Circle Destructor
Circle::~Circle() {
    std::cout << "~Circle()" << std::endl;
    Shape::~Shape();
}

// Circle::calcArea implementation
double Circle::calcArea() const {
    return M_PI * radius * radius;
}
