#include <iostream>
#include <fstream>
#include <string>
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

int main(int argc, char* argv[]) {
    if (argc != 3) {
        return 1;
    }

    std::string inputFileName = argv[1];
    std::string outputFileName = argv[2];

    std::ifstream inputFile(inputFileName);
    if (!inputFile.is_open()) {
        return 1;
    }

    std::ofstream outputFile(outputFileName);
    if (!outputFile.is_open()) {
        inputFile.close();
        return 1;
    }

    // Redirect std::cout to the output file
    std::streambuf* coutBuf = std::cout.rdbuf();
    std::cout.rdbuf(outputFile.rdbuf());

    double radius, width, height, sideLength;

    if (!(inputFile >> radius)) return 1;
    if (!(inputFile >> width >> height)) return 1;
    if (!(inputFile >> sideLength)) return 1;

    {
        // Scope for Circle, Rectangle, and Square to ensure correct destruction order
        Circle circle(radius);
        std::cout << circle.calcArea() << std::endl;

        Rectangle rect(width, height);
        std::cout << rect.calcArea() << std::endl;

        Square square(sideLength);
        std::cout << square.calcArea() << std::endl;
    }

    // Restore std::cout
    std::cout.rdbuf(coutBuf);

    inputFile.close();
    outputFile.close();

    return 0;
}
