#include "Shape.h"
#include <iostream>

Shape::Shape() {
    std::cout << "Shape()" << std::endl;
}

Shape::~Shape() {
    std::cout << "~Shape()" << std::endl;
}

double Shape::calcArea() {
    return 0.0;
}
