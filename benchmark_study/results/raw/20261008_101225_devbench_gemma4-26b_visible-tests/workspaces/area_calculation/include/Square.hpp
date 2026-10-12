#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    Square() : Rectangle(0, 0) {
        std::cout << "Square(0)" << std::endl;
    }
    Square(double _l) : Rectangle(_l, _l) {
        std::cout << "Square(" << _l << ")" << std::endl;
    }
    ~Square() {
        std::cout << "~Square()" << std::endl;
    }
};

#endif
