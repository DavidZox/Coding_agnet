#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include "../include/Circle.hpp"
#include "../include/Rectangle.h"
#include "../include/Square.hpp"

int main(int argc, char* argv[]) {
    if (argc == 2 && std::string(argv[1]) == "--help") {
        return 0;
    }

    if (argc != 3) {
        return 1;
    }

    std::string input_filename = argv[1];
    std::string output_filename = argv[2];

    std::ifstream input_file(input_filename);
    if (!input_file.is_open()) {
        return 1;
    }

    double radius, width, height, side_length;
    if (!(input_file >> radius >> width >> height >> side_length)) {
        return 1;
    }
    input_file.close();

    std::ofstream output_file(output_filename);
    if (!output_file.is_open()) {
        return 1;
    }

    // Redirect std::cout to the output file to capture constructor/destructor messages
    std::streambuf* cout_buf = std::cout.rdbuf();
    std::cout.rdbuf(output_file.rdbuf());

    {
        Circle circle(radius);
        output_file << circle.calcArea() << "\n";
        Rectangle rectangle(width, height);
        output_file << rectangle.calcArea() << "\n";
        Square square(side_length);
        output_file << square.calcArea() << "\n";
    }

    // Restore std::cout
    std::cout.rdbuf(cout_buf);
    output_file.close();

    return 0;
}
