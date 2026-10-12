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

// Shape::calcArea is pure virtual, so it should not be implemented here, 
// but if it were to be implemented (which it shouldn't be for a pure virtual base class), 
// it would be done here. Since it's pure virtual, we rely on derived classes.
