#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    Square() : Rectangle() {}
    ~Square() {
        std::cout << "~Square()" << std::endl;
    }
    Square(double sideLength) : Rectangle(sideLength, sideLength) {
        std::cout << "Square(l)" << std::endl;
    }
    double calcArea() override {
        return Rectangle::calcArea();
    }
};

#endif // SQUARE_HPP
