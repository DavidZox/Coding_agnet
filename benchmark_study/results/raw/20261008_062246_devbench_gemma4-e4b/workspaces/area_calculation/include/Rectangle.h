#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"

class Rectangle : public Shape {
protected:
    double width;
    double height;

public:
    // Constructors
    Rectangle();
    Rectangle(double _w, double _h);

    // Destructor
    ~Rectangle();

    // Overridden function
    double calcArea() const override;
};

#endif // RECTANGLE_H
