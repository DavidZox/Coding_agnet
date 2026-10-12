#include "Circle.hpp"
#include <iostream>
#include <cmath>

Circle::Circle() : radius(0) {
    std::cout << "Circle()" << std::endl;
}

Circle::Circle(double _r) : radius(_r) {
    std::cout << "Circle(" << _r << ")" << std::endl;
}

Circle::~Circle() {
    std::cout << "~Circle()" << std::endl;
}

double Circle::calcArea() {
    return M_PI * radius * radius;
}
