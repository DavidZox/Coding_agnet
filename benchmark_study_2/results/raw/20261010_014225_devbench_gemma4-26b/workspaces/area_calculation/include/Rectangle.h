#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"

class Rectangle : public Shape {
public:
    Rectangle();
    Rectangle(double _w, double _h);
    virtual ~Rectangle();
    double calcArea() override;

private:
    double width;
    double height;
};

#endif
