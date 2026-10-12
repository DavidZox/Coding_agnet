#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    Square() : Rectangle() {}

    Square(double sideLength) : Rectangle(sideLength, sideLength) {
        std::cout << "Square(" << sideLength << ")" << std::endl;
    }

    ~Square() {
        std::cout << "~Square()" << std::endl;
    }

    double calcArea() override {
        return Rectangle::calcArea();
    }
};

#endif
