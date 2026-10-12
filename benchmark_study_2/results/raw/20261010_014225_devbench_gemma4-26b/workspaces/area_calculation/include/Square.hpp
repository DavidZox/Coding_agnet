#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    Square() : Rectangle() {}

    Square(double _l) : Rectangle(_l, _l) {
        std::cout << "Square(l)" << std::endl;
    }

    ~Square() override {
        std::cout << "~Square()" << std::endl;
    }

    double calcArea() override {
        return Rectangle::calcArea();
    }
};

#endif
