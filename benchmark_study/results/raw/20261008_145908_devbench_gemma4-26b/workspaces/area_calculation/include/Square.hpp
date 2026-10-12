#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    Square() : Rectangle() {}

    Square(double l) : Rectangle(l, l) {
        std::cout << "Square(l)" << std::endl;
    }

    ~Square() {
        std::cout << "~Square()" << std::endl;
    }

    double calcArea() override {
        return Rectangle::calcArea();
    }
};

#endif
