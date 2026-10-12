#include <iostream>
#include <fstream>
#include <string>
#include "Shape.h"
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <input_file> <output_file>" << std::endl;
        return 1;
    }

    std::ifstream inputFile(argv[1]);
    if (!inputFile.is_open()) {
        std::cerr << "Error opening input file: " << argv[1] << std::endl;
        return 1;
    }

    std::ofstream outputFile(argv[2]);
    if (!outputFile.is_open()) {
        std::cerr << "Error opening output file: " << argv[2] << std::endl;
        return 1;
    }

    double radius, width, height, sideLength;

    inputFile >> radius;
    Circle circle(radius);
    outputFile << "Circle area: " << circle.calcArea() << std::endl;

    inputFile >> width >> height;
    Rectangle rectangle(width, height);
    outputFile << "Rectangle area: " << rectangle.calcArea() << std::endl;

    inputFile >> sideLength;
    Square square(sideLength);
    outputFile << "Square area: " << square.calcArea() << std::endl;

    inputFile.close();
    outputFile.close();

    return 0;
}
