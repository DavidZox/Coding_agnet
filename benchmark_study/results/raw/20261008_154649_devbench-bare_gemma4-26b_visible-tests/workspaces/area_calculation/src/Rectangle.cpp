#include "Rectangle.h"
#include <iostream>

Rectangle::Rectangle() : Shape(), width(0.0), height(0.0) {}

Rectangle::Rectangle(double _w, double _h) : Shape(), width(_w), height(_h) {
    std::cout << "Rectangle(" << width << ", " << height << ")" << std::endl;
}

Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

double Rectangle::calcArea() {
    return width * height;
}
