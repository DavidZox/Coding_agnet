#include "Shape.h"
#include <iostream>

// Shape Constructor
Shape::Shape() {
    std::cout << "Shape()" << std::endl;
}

// Shape Destructor
Shape::~Shape() {
    std::cout << "~Shape()" << std::endl;
}

// Note: calcArea is pure virtual in Shape.h, so it cannot be implemented here.
// The implementation for derived classes will handle the actual area calculation.
