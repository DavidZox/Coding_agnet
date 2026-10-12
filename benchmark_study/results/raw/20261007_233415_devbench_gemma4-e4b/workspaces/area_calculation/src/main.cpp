#include <iostream>
#include <fstream>
#include <cmath>

#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <input_filename> <output_filename>" << std::endl;
        return 1;
    }

    std::string input_filename = argv[1];
    std::string output_filename = argv[2];

    std::ifstream infile(input_filename);
    if (!infile.is_open()) {
        std::cerr << "Error: Could not open input file " << input_filename << std::endl;
        return 1;
    }

    double radius, width, height, sideLength;

    // Read dimensions: radius, width, height, square height
    if (!(infile >> radius >> width >> height >> sideLength)) {
        std::cerr << "Error: Could not read all dimensions from input file." << std::endl;
        infile.close();
        return 1;
    }
    infile.close();

    // Create shapes
    // Note: The sequence diagram suggests a specific creation order and interaction,
    // but the PRD specifies reading 4 values for Circle, Rectangle, Square.
    // We will instantiate them based on the read values.

    // Circle
    Circle circle(radius);
    double area_circle = circle.calcArea();

    // Rectangle
    Rectangle rectangle(width, height);
    double area_rectangle = rectangle.calcArea();

    // Square (inherits from Rectangle, but we use its specific constructor/logic)
    // The PRD states: "i.e. 4 numbers: radius, width, height, square height."
    // We use sideLength for the square.
    Square square(sideLength);
    double area_square = square.calcArea();

    // Write results to output file
    std::ofstream outfile(output_filename);
    if (!outfile.is_open()) {
        std::cerr << "Error: Could not open output file " << output_filename << std::endl;
        return 1;
    }

    // Write areas in the expected order (Circle, Rectangle, Square)
    outfile << area_circle << "\n";
    outfile << area_rectangle << "\n";
    outfile << area_square << "\n";

    outfile.close();

    return 0;
}
