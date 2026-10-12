#include <iostream>
#include <fstream>
#include <stdexcept>
#include "Shape.h"
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <input_file> <output_file>" << std::endl;
        return 1;
    }

    const char* inputFileName = argv[1];
    const char* outputFileName = argv[2];

    std::ifstream inputFile(inputFileName);
    if (!inputFile.is_open()) {
        std::cerr << "Error opening input file: " << inputFileName << std::endl;
        return 1;
    }

    std::ofstream outputFile(outputFileName);
    if (!outputFile.is_open()) {
        std::cerr << "Error opening output file: " << outputFileName << std::endl;
        return 1;
    }

    double radius, width, height, sideLength;

    if (!(inputFile >> radius >> width >> height >> sideLength)) {
        std::cerr << "Error reading dimensions from input file." << std::endl;
        return 1;
    }

    Circle circle(radius);
    Rectangle rectangle(width, height);
    Square square(sideLength);

    outputFile << "Circle area: " << circle.calcArea() << std::endl;
    outputFile << "Rectangle area: " << rectangle.calcArea() << std::endl;
    outputFile << "Square area: " << square.calcArea() << std::endl;

    inputFile.close();
    outputFile.close();

    return 0;
}
