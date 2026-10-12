#include "Shape.h"
#include "Circle.hpp"

Shape::Shape() {
    std::cout << "Shape()" << std::endl;
}

Shape::~Shape() {
    std::cout << "~Shape()" << std::endl;
}

double Shape::calcArea() {
    return 0.0;
}

Circle::Circle() : radius(0.0) {
    std::cout << "Circle(0)" << std::endl;
}

Circle::Circle(double _r) : radius(_r) {
    std::cout << "Circle(" << radius << ")" << std::endl;
}

Circle::~Circle() {
    std::cout << "~Circle()" << std::endl;
}

double Circle::calcArea() {
    return 3.14159265358979323846 * radius * radius;
}
