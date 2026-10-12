#include "Square.hpp"
#include <iostream>

// Square Default Constructor
Square::Square() : Rectangle() {
    // The base constructor calls Shape(), which is handled by Rectangle's constructor chain.
    // We only need to print the specific Square message here, assuming Rectangle's constructor handles Shape().
    // Based on UML sequence, Square calls Rectangle constructor, which calls Shape constructor.
    // We rely on the chain: Square -> Rectangle -> Shape.
    // Since Rectangle constructor prints "Rectangle(0, 0)", we just need to ensure the Square specific message is printed if required, 
    // but the requirement states: "Square(l)" where l is the side length. For default, l=0.
    // We must ensure the constructor chain prints the required messages.
    // If we call Rectangle(), it prints Rectangle(0, 0). We need to override/add the Square specific message.
    // Given the UML sequence implies Square calls Rectangle, and Rectangle calls Shape, we must ensure the output matches.
    // Let's assume the specific message for Square is printed *after* the base chain completes, or that the base chain is sufficient if l=0.
    // To strictly follow the output requirement for Square(l), we must ensure the constructor prints it.
    // Since Square inherits Rectangle, and Rectangle prints Rectangle(w, h), we must override or adjust.
    // For simplicity and adhering to the structure, we rely on the chain and add the specific message if needed, 
    // but since the prompt implies the derived class constructor prints its specific message, we add it here.
    std::cout << "Square(0)" << std::endl;
}

// Square Parameterized Constructor
Square::Square(double _l) : Rectangle(_l, _l) {
    // Rectangle constructor prints Rectangle(_l, _l). We must ensure Square(_l) is also printed.
    std::cout << "Square(" << _l << ")" << std::endl;
}

// Square Destructor
Square::~Square() {
    std::cout << "~Square()" << std::endl;
    Rectangle::~Rectangle(); // Explicitly call base destructor
}

// Square::calcArea implementation
double Square::calcArea() const {
    // Since Square inherits from Rectangle, and Rectangle::calcArea is w*h, 
    // and for a square w=h=l, this is correct. We can rely on the inherited implementation.
    return Rectangle::calcArea();
}
