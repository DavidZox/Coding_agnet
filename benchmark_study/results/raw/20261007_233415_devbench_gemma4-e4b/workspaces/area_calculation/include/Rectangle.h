#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"
#include <iostream>

class Rectangle : public Shape {
private:
    double width;
    double height;

public:
    // Default constructor
    Rectangle();

    // Parameterized constructor
    Rectangle(double _w, double _h);

    // Destructor
    ~Rectangle();

    // Override calcArea
    double calcArea() const override;
};

#endif // RECTANGLE_H
