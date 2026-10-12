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

// Shape::calcArea is pure virtual in Shape.h, so it cannot be implemented here
// unless we change Shape.h to not be abstract, but based on PRD, it should be abstract.
// If we must implement it, we'd need to change Shape.h to not have = 0.
// Since Shape.h defines it as pure virtual (double calcArea() const = 0;),
// we only need to implement the constructor and destructor here.
