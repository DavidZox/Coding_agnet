#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"

class Rectangle : public Shape {
private:
    double width;
    double height;

public:
    Rectangle();
    Rectangle(double w, double h);
    virtual ~Rectangle();
    double calcArea() override;
};

#endif
