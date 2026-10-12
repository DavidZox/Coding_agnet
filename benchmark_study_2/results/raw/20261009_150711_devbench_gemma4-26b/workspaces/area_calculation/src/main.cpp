#include <iostream>
#include <fstream>
#include <vector>
#include <memory>
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <input_file> <output_file>" << std::endl;
        return 1;
    }

    std::string input_filename = argv[1];
    std::string output_filename = argv[2];

    std::ifstream input_file(input_filename);
    if (!input_file.is_open()) {
        std::cerr << "Error: Could not open input file " << input_filename << std::endl;
        return 1;
    }

    double radius, width, height, side;
    if (!(input_file >> radius >> width >> height >> side)) {
        std::cerr << "Error: Invalid input data in " << input_filename << std::endl;
        return 1;
    }
    input_file.close();

    std::ofstream output_file(output_filename);
    if (!output_file.is_open()) {
        std::cerr << "Error: Could not open output file " << output_filename << std::endl;
        return 1;
    }

    // Using unique_ptr to manage lifetime and ensure destructors are called
    // The sequence of creation and destruction is important for the output messages
    {
        std::unique_ptr<Circle> circle = std::make_unique<Circle>(radius);
        std::unique_ptr<Rectangle> rectangle = std::make_unique<Rectangle>(width, height);
        std::unique_ptr<Square> square = std::make_unique<Square>(side);

        output_file << circle->calcArea() << std::endl;
        output_file << rectangle->calcArea() << std::endl;
        output_file << square->calcArea() << std::endl;
    }

    output_file.close();

    return 0;
}
