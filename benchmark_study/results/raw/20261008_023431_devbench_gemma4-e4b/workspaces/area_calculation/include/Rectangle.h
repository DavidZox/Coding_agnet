#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"

class Rectangle : public Shape {
protected:
    double width;
    double height;

public:
    // Constructors and Destructors
    Rectangle();
    Rectangle(double _w, double _h);
    ~Rectangle();

    // Overridden Function
    double calcArea() override;
};

#endif // RECTANGLE_H
