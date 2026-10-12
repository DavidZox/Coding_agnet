#include "Rectangle.h"
#include <iostream>

Rectangle::Rectangle() : width(0.0), height(0.0) {
    std::cout << "Rectangle(0, 0)" << std::endl;
}

Rectangle::Rectangle(double _w, double _h) : width(_w), height(_h) {
    std::cout << "Rectangle(w, h)" << std::endl;
}

Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

double Rectangle::calcArea() {
    return width * height;
}
