#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"

class Square : public Rectangle {
public:
    Square();
    Square(double sideLength);
    ~Square();

    double calcArea() override;
};

#endif // SQUARE_HPP
