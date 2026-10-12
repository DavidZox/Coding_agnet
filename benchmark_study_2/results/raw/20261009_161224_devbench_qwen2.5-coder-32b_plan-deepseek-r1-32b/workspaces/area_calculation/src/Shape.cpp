#include "Shape.h"

Shape::Shape() {
    std::cout << "Shape()" << std::endl;
}

Shape::~Shape() {
    std::cout << "~Shape()" << std::endl;
}

double Shape::calcArea() {
    return 0.0;
}
