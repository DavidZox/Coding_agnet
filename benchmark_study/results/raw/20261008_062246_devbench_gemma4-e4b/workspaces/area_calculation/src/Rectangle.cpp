#include "Rectangle.h"
#include <iostream>

// Constructor implementations
Rectangle::Rectangle() : width(0.0), height(0.0) {
    std::cout << "Rectangle(0, 0)" << std::endl;
}

Rectangle::Rectangle(double _w, double _h) : width(_w), height(_h) {
    std::cout << "Rectangle(" << _w << ", " << _h << ")" << std::endl;
}

// Destructor implementation
Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

// Overridden calcArea implementation
double Rectangle::calcArea() const {
    return width * height;
}
