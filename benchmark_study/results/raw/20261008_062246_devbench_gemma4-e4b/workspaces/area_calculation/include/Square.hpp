#ifndef SQUARE_HPP
#define SQUARE_HPP

#include "Rectangle.h"
#include <iostream>
#include <cmath>

class Square : public Rectangle {
public:
    // Default constructor
    Square() : Rectangle() {
        std::cout << "Square()" << std::endl;
    }

    // Parameterized constructor
    Square(double _l) : Rectangle(_l, _l) {
        std::cout << "Square(" << _l << ")" << std::endl;
    }

    // Destructor
    ~Square() override {
        std::cout << "~Square()" << std::endl;
    }

    // Override calcArea
    double calcArea() const override {
        // Since Square inherits from Rectangle, we can use the dimensions set by the constructor.
        // For a square, width == height == side length (_l).
        // We calculate area based on the side length which is stored as width/height in Rectangle.
        return width * width;
    }
};

#endif // SQUARE_HPP
