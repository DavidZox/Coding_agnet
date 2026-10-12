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
        std::cerr << "Error: Failed to read dimensions from input file." << std::endl;
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

    // Using scope to ensure destructors are called before writing to file if needed,
    // but PRD implies we calculate and then write.
    // To match the sequence of constructor/destructor outputs in console, 
    // we create them in a block.
    {
        // To match the expected output format where constructors are printed with specific placeholders
        // like Circle(r), we must ensure the classes themselves print the correct strings.
        // Since we cannot change the classes here, we rely on their implementation.
        
        // The diff showed that the expected output contains the constructor/destructor messages.
        // The diff showed that the current output (the areas) is at the start of the file, 
        // and the expected output has the messages.
        // This means the expected file has the messages BEFORE the areas.
        
        // Let's try: 
        // 1. Create objects (prints constructors)
        // 2. Calculate areas (print areas)
        // 3. Destroy objects (prints destructors)
        // All via std::cout (which is redirected to output_file).

        // To ensure areas are printed AFTER constructors but BEFORE destructors:
        // We use unique_ptr to manage lifetime, but we need to control the exact order.
        
        // Step 1: Create Circle
        std::unique_ptr<Circle> circle = std::make_unique<Circle>(radius);
        double circle_area = circle->calcArea();
        std::cout << circle_area << std::endl;

        // Step 2: Create Rectangle
        std::unique_ptr<Rectangle> rectangle = std::make_unique<Rectangle>(width, height);
        double rect_area = rectangle->calcArea();
        std::cout << rect_area << std::endl;

        // Step 3: Create Square
        std::unique_ptr<Square> square = std::make_unique<Square>(side);
        double square_area = square->calcArea();
        std::cout << square_area << std::endl;

        // Step 4: Print areas (Already printed above to match the "area follows constructor" requirement)
        // Step 5: Destroy objects in reverse order of creation to match typical stack behavior
        // or specific expected sequence. The diff shows: ~Square, ~Rectangle, ~Shape, ~Rectangle, ~Shape, ~Circle, ~Shape.
        // This implies Square is destroyed, then Rectangle, then Circle.
        // However, unique_ptr in a block will destroy in reverse order of declaration: square, rectangle, circle.
        // Let's check the diff again.
        // Expected: ~Square, ~Rectangle, ~Shape, ~Rectangle, ~Shape, ~Circle, ~Shape.
        // This matches: Square (destroys Rectangle/Shape), then Rectangle (destroys Shape), then Circle (destroys Shape).
        // This is exactly what happens when unique_ptrs are destroyed in reverse order of declaration.
    }

    // Restore std::cout
    std::cout.rdbuf(cout_buf);
    output_file.close();

    return 0;
}
