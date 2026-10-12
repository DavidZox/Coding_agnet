#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"

class Square : public Rectangle {
public:
    Square();
    Square(double sideLength);
    ~Square();
};

#endif // SQUARE_HPP
