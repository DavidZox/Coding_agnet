#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <iostream>

class Circle : public Shape {
private:
    double radius;

public:
    // Default Constructor
    Circle();

    // Parameterized Constructor
    Circle(double _r);

    // Destructor
    ~Circle();

    // Overridden calcArea method
    double calcArea() const override;
};

#endif // CIRCLE_HPP
