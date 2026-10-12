#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"
#include <iostream>

class Rectangle : public Shape {
private:
    double width;
    double height;

public:
    // Default Constructor
    Rectangle();

    // Parameterized Constructor
    Rectangle(double _w, double _h);

    // Destructor
    ~Rectangle();

    // Overridden calcArea method
    double calcArea() const override;
};

#endif // RECTANGLE_H
