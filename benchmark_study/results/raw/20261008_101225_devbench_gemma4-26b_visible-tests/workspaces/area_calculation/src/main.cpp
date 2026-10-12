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

    double radius, width, height, side_length;
    if (!(input_file >> radius >> width >> height >> side_length)) {
        std::cerr << "Error: Invalid input data in " << input_filename << std::endl;
        return 1;
    }
    input_file.close();

    std::ofstream output_file(output_filename);
    if (!output_file.is_open()) {
        std::cerr << "Error: Could not open output file " << output_filename << std::endl;
        return 1;
    }

    // Redirect std::cout to the output file to capture constructor/destructor messages
    std::streambuf* cout_buf = std::cout.rdbuf();
    std::cout.rdbuf(output_file.rdbuf());

    // Create shapes using smart pointers to ensure proper destructor calls
    // The order of creation and destruction matters for the console output requirements
    {
        std::unique_ptr<Shape> circle = std::make_unique<Circle>(radius);
        std::unique_ptr<Shape> rectangle = std::make_unique<Rectangle>(width, height);
        std::unique_ptr<Shape> square = std::make_unique<Square>(side_length);

        // Write areas to the output file
        // Note: calcArea() in the classes might also print to std::cout, 
        // which is now redirected to output_file.
        // However, the PRD says "write the results to the specified output file".
        // Based on the requirement to capture constructor/destructor messages, 
        // we must ensure the area values themselves are also in the file.
        
        // Since the classes' calcArea() might print to cout, we need to be careful.
        // If calcArea() returns the value, we write it to output_file.
        // If calcArea() prints to cout, it will go to output_file.
        // Let's assume calcArea() returns the value and we write it.
        
        // To ensure the area values are written to the file correctly alongside the messages:
        // We use the redirected cout for the messages and the file stream for the values.
        // But the requirement says "write the results to the specified output file".
        // If we want the areas to be in the file, we can write them to cout (which is redirected).
        
        std::cout << circle->calcArea() << "\n";
        std::cout << rectangle->calcArea() << "\n";
        std::cout << square->calcArea() << "\n";
    }

    // Restore std::cout
    std::cout.rdbuf(cout_buf);

    output_file.close();

    return 0;
}
