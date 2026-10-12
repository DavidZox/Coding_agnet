#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>

class Circle : public Shape {
private:
    double radius;

public:
    Circle();
    Circle(double _r);
    ~Circle();
    double calcArea() override;
};

#endif // CIRCLE_HPP
