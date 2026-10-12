#include "Square.hpp"
#include <iostream>
#include <cmath>

// Constructor implementations
Square::Square() : Rectangle() {
    std::cout << "Square()" << std::endl;
}

Square::Square(double _l) : Rectangle(_l, _l) {
    std::cout << "Square(" << _l << ")" << std::endl;
}

// Destructor implementation
Square::~Square() {
    std::cout << "~Square()" << std::endl;
}

// Overridden calcArea implementation
double Square::calcArea() {
    // Since Square inherits from Rectangle, we can use Rectangle's logic or recalculate.
    // Based on the inheritance and PRD, we should calculate the area based on its side length.
    // If we rely on Rectangle's implementation, we need to ensure width and height are set correctly.
    // For simplicity and adherence to the structure, we use the side length logic.
    // Assuming the side length is stored in width/height from the constructor call to Rectangle.
    return width * height;
}
