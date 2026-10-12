#include "Rectangle.h"
#include <iostream>

// Rectangle Constructor
Rectangle::Rectangle() : width(0.0), height(0.0) {
    std::cout << "Rectangle(0, 0)" << std::endl;
}

// Rectangle Parameterized Constructor
Rectangle::Rectangle(double _w, double _h) : width(_w), height(_h) {
    std::cout << "Rectangle(" << _w << ", " << _h << ")" << std::endl;
}

// Rectangle Destructor
Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

// Rectangle::calcArea implementation
double Rectangle::calcArea() const {
    return width * height;
}
