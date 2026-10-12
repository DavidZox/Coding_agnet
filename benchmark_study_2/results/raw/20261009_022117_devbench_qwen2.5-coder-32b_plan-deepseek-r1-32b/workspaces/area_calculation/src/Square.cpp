#include "Square.hpp"
#include <iostream>

Square::Square() : Rectangle() {
    std::cout << "Square()" << std::endl;
}

Square::Square(double sideLength) : Rectangle(sideLength, sideLength) {
    std::cout << "Square(" << sideLength << ")" << std::endl;
}

Square::~Square() {
    std::cout << "~Square()" << std::endl;
}

double Square::calcArea() {
    return Rectangle::calcArea();
}
