#include "Rectangle.h"
#include <iostream>

Rectangle::Rectangle() : width(0.0), height(0.0) {}

Rectangle::Rectangle(double w, double h) : width(w), height(h) {
    std::cout << "Rectangle(w, h)" << std::endl;
}

Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

double Rectangle::calcArea() {
    return width * height;
}
