#include "Rectangle.h"
#include "Shape.h"
#include <iostream>

// Constructor implementation
Rectangle::Rectangle() : Shape() {
    width = 0.0;
    height = 0.0;
    std::cout << "Rectangle(0, 0)" << std::endl;
}

Rectangle::Rectangle(double _w, double _h) : Shape() {
    width = _w;
    height = _h;
    std::cout << "Rectangle(" << _w << ", " << _h << ")" << std::endl;
}

// Destructor implementation
Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

// Area calculation implementation
double Rectangle::calcArea() const {
    return width * height;
}
