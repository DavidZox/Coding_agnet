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

// Shape::calcArea is pure virtual, so no implementation needed here, 
// but if it were not pure virtual, the implementation would go here.
// Since it is pure virtual (indicated by = 0 in Shape.h), this file only needs to define the constructor/destructor.
