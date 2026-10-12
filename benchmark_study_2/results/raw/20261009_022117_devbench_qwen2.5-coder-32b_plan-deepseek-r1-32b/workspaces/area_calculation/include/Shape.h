#ifndef SHAPE_H
#define SHAPE_H

#include <iostream>

class Shape {
public:
    Shape();
    virtual ~Shape();
    virtual double calcArea() = 0;
};

#endif // SHAPE_H
