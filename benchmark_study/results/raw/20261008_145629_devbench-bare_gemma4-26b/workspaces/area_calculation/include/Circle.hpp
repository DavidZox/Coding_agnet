#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>

class Circle : public Shape {
private:
    double radius;

public:
    Circle();
    ~Circle();
    Circle(double _r);
    double calcArea() override;
};

#endif // CIRCLE_HPP
