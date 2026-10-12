#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    Square();
    ~Square();
    Square(double _l);
};

#endif // SQUARE_HPP
