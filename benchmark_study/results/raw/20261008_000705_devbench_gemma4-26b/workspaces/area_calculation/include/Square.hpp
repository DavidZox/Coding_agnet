#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    Square() : Rectangle() {
        std::cout << "Square()" << std::endl;
    }

    Square(double sideLength) : Rectangle(sideLength, sideLength) {
        std::cout << "Square(" << sideLength << ")" << std::endl;
    }

    ~Square() {
        std::cout << "~Square()" << std::endl;
    }
};

#endif
