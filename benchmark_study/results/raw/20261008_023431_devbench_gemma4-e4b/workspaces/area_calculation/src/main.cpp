#include <iostream>
#include <fstream>
#include <vector>
#include <cmath>
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

using namespace std;

int main(int argc, char* argv[]) {
    if (argc != 3) {
        cerr << "Usage: " << argv[0] << " <input_filename> <output_filename>" << endl;
        return 1;
    }

    string input_filename = argv[1];
    string output_filename = argv[2];

    ifstream infile(input_filename);
    if (!infile.is_open()) {
        cerr << "Error: Could not open input file " << input_filename << endl;
        return 1;
    }

    double radius, width, height, side_length;

    // Read dimensions: radius, width, height, square side_length
    if (!(infile >> radius >> width >> height >> side_length)) {
        cerr << "Error: Could not read all dimensions from input file." << endl;
        infile.close();
        return 1;
    }
    infile.close();

    // Create shapes using parameterized constructors
    // Note: The UML suggests Square inherits from Rectangle, but PRD implies specific dimension reading.
    // We follow the PRD requirement: read 4 numbers (r, w, h, l) and create the shapes.
    // We must use the constructors that take parameters.

    // Circle
    Circle circle(radius);

    // Rectangle
    Rectangle rectangle(width, height);

    // Square (Inherits from Rectangle, so we use the appropriate constructor chain)
    // Since Square inherits from Rectangle, and the PRD implies Square takes a side length 'l',
    // we instantiate it using the constructor that takes a side length.
    // Based on UML_class.md: Square inherits Rectangle.
    // Based on PRD: "i.e. 4 numbers: radius, width, height, square height." (This is ambiguous, but we use side_length for Square)
    // We instantiate Square using its constructor: Square(double _l)
    Square square(side_length);


    // Calculate areas
    double area_circle = circle.calcArea();
    double area_rectangle = rectangle.calcArea();
    double area_square = square.calcArea();

    // Write results to output file
    ofstream outfile(output_filename);
    if (!outfile.is_open()) {
        cerr << "Error: Could not open output file " << output_filename << endl;
        return 1;
    }

    // Output format is not strictly defined for the output file content, 
    // but we write the calculated areas.
    outfile << "Circle Area: " << area_circle << endl;
    outfile << "Rectangle Area: " << area_rectangle << endl;
    outfile << "Square Area: " << area_square << endl;

    outfile.close();

    // Destructors will be called automatically when objects go out of scope
    return 0;
}
