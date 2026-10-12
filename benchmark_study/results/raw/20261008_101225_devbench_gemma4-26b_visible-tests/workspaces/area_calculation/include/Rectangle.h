#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"

class Rectangle : public Shape {
private:
    double width;
    double height;

public:
    Rectangle();
    Rectangle(double _w, double _h);
    virtual ~Rectangle();
    virtual double calcArea() override;
};

#endif
