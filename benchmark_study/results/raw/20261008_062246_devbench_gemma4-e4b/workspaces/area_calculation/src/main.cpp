#include <iostream>
#include <fstream>
#include <string>
#include <cmath>
#include <memory> // Required for std::unique_ptr
#include "Shape.h"
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

using namespace std;

int main(int argc, char* argv[]) {
    if (argc != 3) {
        cerr << "Usage: " << argv[0] << " <input_filename> <output_filename>" << endl;
        return 1;
    }

    string inputFilename = argv[1];
    string outputFilename = argv[2];

    ifstream inputFile(inputFilename);
    if (!inputFile.is_open()) {
        cerr << "Error: Could not open input file " << inputFilename << endl;
        return 1;
    }

    ofstream outputFile(outputFilename);
    if (!outputFile.is_open()) {
        cerr << "Error: Could not open output file " << outputFilename << endl;
        return 1;
    }

    // Read dimensions: radius, width, height, square sideLength
    double radius, width, height, sideLength;

    if (!(inputFile >> radius >> width >> height >> sideLength)) {
        cerr << "Error: Failed to read all dimensions from input file." << endl;
        inputFile.close();
        outputFile.close();
        return 1;
    }

    // Create shapes and calculate areas
    // Note: The sequence diagram suggests creating objects and then calling calcArea().
    // We must ensure proper memory management (using smart pointers or manual deletion).
    // Since the requirements imply a sequence of operations, we will use unique_ptr for safety.

    // Construction order: Circle, Rectangle, Square (Square inherits from Rectangle)
    // The constructors will print their required messages.
    unique_ptr<Shape> circle = make_unique<Circle>(radius);
    unique_ptr<Shape> rectangle = make_unique<Rectangle>(width, height);
    // Square inherits from Rectangle, so we use the specific constructor for Square
    unique_ptr<Shape> square = make_unique<Square>(sideLength);

    // Calculate areas
    double areaCircle = circle->calcArea();
    double areaRectangle = rectangle->calcArea();
    double areaSquare = square->calcArea();

    // Write results to output file
    outputFile << "Circle Area: " << areaCircle << endl;
    outputFile << "Rectangle Area: " << areaRectangle << endl;
    outputFile << "Square Area: " << areaSquare << endl;

    // Objects are automatically destroyed when unique_ptr goes out of scope,
    // triggering destructors in reverse order of construction (Square, Rectangle, Circle).

    inputFile.close();
    outputFile.close();

    return 0;
}
