#include "Rectangle.h"
#include <iostream>

Rectangle::Rectangle() : Shape(), width(0.0), height(0.0) {}

Rectangle::Rectangle(double width, double height) : Shape(), width(width), height(height) {
    std::cout << "Rectangle(w, h)" << std::endl;
}

Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

double Rectangle::calcArea() {
    return width * height;
}
