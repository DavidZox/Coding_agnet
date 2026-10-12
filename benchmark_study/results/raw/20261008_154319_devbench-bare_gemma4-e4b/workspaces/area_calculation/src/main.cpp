#include <iostream>
#include <fstream>
#include <vector>
#include <cmath>

#include "Shape.h"
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

// Function to process the shapes based on input file
void processShapes(const std::string& inputFile, const std::string& outputFile) {
    std::ifstream inFile(inputFile);
    std::ofstream outFile(outputFile);

    if (!inFile.is_open()) {
        std::cerr << "Error: Could not open input file: " << inputFile << std::endl;
        return;
    }

    if (!outFile.is_open()) {
        std::cerr << "Error: Could not open output file: " << outputFile << std::endl;
        return;
    }

    // Read dimensions: radius, width, height, side length
    double radius, width, height, sideLength;

    // Read Circle dimensions
    if (!(inFile >> radius)) {
        std::cerr << "Error: Failed to read Circle radius from input file." << std::endl;
        return;
    }

    // Read Rectangle dimensions
    if (!(inFile >> width >> height)) {
        std::cerr << "Error: Failed to read Rectangle dimensions from input file." << std::endl;
        return;
    }

    // Read Square dimensions (side length)
    if (!(inFile >> sideLength)) {
        std::cerr << "Error: Failed to read Square side length from input file." << std::endl;
        return;
    }

    // Use smart pointers or unique_ptr for proper memory management, 
    // but sticking to raw pointers/stack allocation based on typical simple examples 
    // unless dynamic allocation is strictly required by the prompt structure.
    // Since we need to manage the lifecycle for destructors to print, we use unique_ptr.

    std::unique_ptr<Shape> circle = std::make_unique<Circle>(radius);
    std::unique_ptr<Shape> rectangle = std::make_unique<Rectangle>(width, height);
    std::unique_ptr<Shape> square = std::make_unique<Square>(sideLength);

    // Calculate areas
    double areaCircle = circle->calcArea();
    double areaRectangle = rectangle->calcArea();
    double areaSquare = square->calcArea();

    // Write results to output file
    outFile << "Circle Area: " << areaCircle << std::endl;
    outFile << "Rectangle Area: " << areaRectangle << std::endl;
    outFile << "Square Area: " << areaSquare << std::endl;

    std::cout << "Successfully processed shapes. Results written to " << outputFile << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <input_filename> <output_filename>" << std::endl;
        return 1;
    }

    std::string inputFile = argv[1];
    std::string outputFile = argv[2];

    processShapes(inputFile, outputFile);

    return 0;
}
