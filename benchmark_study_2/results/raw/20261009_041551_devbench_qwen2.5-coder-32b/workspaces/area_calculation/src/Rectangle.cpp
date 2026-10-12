#include "Rectangle.h"
#include <iostream>

Rectangle::Rectangle() : width(0), height(0) {
    std::cout << "Rectangle()" << std::endl;
}

Rectangle::Rectangle(double _w, double _h) : width(_w), height(_h) {
    std::cout << "Rectangle(" << _w << ", " << _h << ")" << std::endl;
}

Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

double Rectangle::calcArea() {
    return width * height;
}
