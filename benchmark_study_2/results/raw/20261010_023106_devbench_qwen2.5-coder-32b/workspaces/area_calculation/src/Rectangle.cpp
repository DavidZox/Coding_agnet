#include "Rectangle.h"
#include "Square.hpp"
#include <iostream>

Rectangle::Rectangle() : width(0), height(0) {
    std::cout << "Rectangle()" << std::endl;
}

Rectangle::Rectangle(double _w, double _h) : width(_w), height(_h) {
    std::cout << "Rectangle(" << width << ", " << height << ")" << std::endl;
}

Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

double Rectangle::calcArea() {
    return width * height;
}

Square::Square() : Rectangle() {
    std::cout << "Square()" << std::endl;
}

Square::Square(double sideLength) : Rectangle(sideLength, sideLength) {
    std::cout << "Square(" << sideLength << ")" << std::endl;
}

Square::~Square() {
    std::cout << "~Square()" << std::endl;
}
