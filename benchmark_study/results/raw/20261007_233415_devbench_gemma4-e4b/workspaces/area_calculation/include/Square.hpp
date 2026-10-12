#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>
#include <cmath> // For std::pow if needed, but l*l is simpler

class Square : public Rectangle {
private:
    double sideLength;

public:
    // Default constructor
    Square();

    // Parameterized constructor
    Square(double _l);

    // Destructor
    ~Square();

    // calcArea (no override keyword as per compiler error)
    double calcArea();
};

// Implementation details moved here as per instruction context (no src/Square.cpp provided)

// Default constructor implementation
Square::Square() : Rectangle() {
    // Default constructor output is not explicitly defined for Square, 
    // but we must ensure base class constructors are called.
}

// Parameterized constructor implementation
Square::Square(double _l) : Rectangle(0.0, 0.0), sideLength(_l) {
    std::cout << "Square(" << _l << ")" << std::endl;
}

// Destructor implementation
Square::~Square() {
    std::cout << "~Square()" << std::endl;
}

// calcArea implementation
double Square::calcArea() {
    return sideLength * sideLength;
}

#endif // SQUARE_HPP
