#ifndef CIRCLE_HPP
#define CIRCLE_HPP

#include "Shape.h"
#include <cmath>

class Circle : public Shape {
private:
    double radius;

public:
    // Default constructor
    Circle();

    // Parameterized constructor
    Circle(double _r);

    // Destructor
    ~Circle();

    // Override calcArea
    double calcArea() override;
};

#endif // CIRCLE_HPP
