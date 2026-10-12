#ifndef SHAPE_H
#define SHAPE_H

#include <iostream>

class Shape {
protected:
    Shape();
    virtual ~Shape();
public:
    virtual double calcArea() = 0;
};

#endif // SHAPE_H
