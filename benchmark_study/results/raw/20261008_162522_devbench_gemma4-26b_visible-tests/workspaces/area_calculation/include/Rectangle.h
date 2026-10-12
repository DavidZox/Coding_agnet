#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"

class Rectangle : public Shape {
public:
    Rectangle();
    ~Rectangle();
    Rectangle(double width, double height);
    double calcArea() override;

protected:
    double width;
    double height;
};

#endif // RECTANGLE_H
