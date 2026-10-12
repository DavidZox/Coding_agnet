#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>

class Square : public Rectangle {
public:
    // Default Constructor
    Square();

    // Parameterized Constructor
    Square(double _l);

    // Destructor
    ~Square();

    // Overridden calcArea method (Inherits from Rectangle, which inherits from Shape)
    // Note: UML sequence suggests Square calls Rectangle::calcArea(), but since it inherits, 
    // it should override or use the base implementation if it doesn't need specific logic.
    // Based on the UML_class.md, Square inherits from Rectangle, and it should implement calcArea.
    // Since Rectangle already has calcArea, we might just rely on inheritance, but for completeness 
    // and adherence to the structure, we define it.
    double calcArea() const override;
};

#endif // SQUARE_HPP
