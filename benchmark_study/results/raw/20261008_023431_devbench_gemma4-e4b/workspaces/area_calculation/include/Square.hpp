#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"

class Square : public Rectangle {
public:
    // Constructors
    Square();
    Square(double _l);

    // Destructor
    ~Square();

    // Overridden function
    double calcArea() override;
};

#endif // SQUARE_HPP
