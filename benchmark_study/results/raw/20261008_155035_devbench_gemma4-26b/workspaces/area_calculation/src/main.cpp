#include <iostream>
#include <fstream>
#include <string>
#include <sstream>
#include <regex>
#include <vector>
#include "../include/Circle.hpp"
#include "../include/Rectangle.h"
#include "../include/Square.hpp"

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <input_file> <output_file>" << std::endl;
        return 1;
    }

    std::string inputFileName = argv[1];
    std::string outputFileName = argv[2];

    std::ifstream inputFile(inputFileName);
    if (!inputFile.is_open()) {
        std::cerr << "Error: Could not open input file " << inputFileName << std::endl;
        return 1;
    }

    double radius, width, height, sideLength;
    if (!(inputFile >> radius >> width >> height >> sideLength)) {
        std::cerr << "Error: Invalid input data in " << inputFileName << std::endl;
        inputFile.close();
        return 1;
    }
    inputFile.close();

    std::ofstream outputFile(outputFileName);
    if (!outputFile.is_open()) {
        std::cerr << "Error: Could not open output file " << outputFileName << std::endl;
        return 1;
    }

    // Redirect std::cout to a stringstream to capture all constructor/destructor messages
    std::stringstream ss;
    std::streambuf* cout_buf = std::cout.rdbuf();
    std::cout.rdbuf(ss.rdbuf());

    // Create objects to trigger constructors and calculate areas
    // We use scopes to ensure destructors are called while cout is still redirected
    {
        Circle circle(radius);
        double circleArea = circle.calcArea();
        // We need to write the area to the output file, but the area calculation 
        // itself doesn't print to cout. The PRD says calcArea() "outputs area", 
        // but the main logic says "write the calculated areas to the specified output file".
        // Based on the diff, the area is written to the file, not cout.
        // However, the diff shows the area is NOT in the captured cout.
        // Let's follow the requirement: "write the results to the specified output file".
        // The diff shows the area is written to the file.
        // Wait, the diff shows the area is NOT in the output file? 
        // No, the diff shows the output file contains the destructor messages.
        // Let's re-read: "After calculating the areas... the program should write the results to the specified output file."
        // The diff shows the output file contains:
        // ~Shape()
        // ~Rectangle()
        // ~Shape()
        // ~Circle()
        // This means the destructor messages (from cout) are being written to the file.
        // And the area values are also in the file.
        // Let's use a separate stream for the area to avoid confusion, 
        // but the destructor messages must be captured.
        
        // To match the diff, we need to capture cout and then write it to the file.
        // But the area must also be in the file.
        // Let's use a custom approach: capture cout, and write area to a temporary buffer.
        // Actually, the simplest way to match the diff:
        // 1. Capture cout in stringstream.
        // 2. Perform logic.
        // 3. Write the captured cout (with regex) to the file.
        // 4. Write the areas to the file.
        // BUT the diff shows destructor messages come AFTER the areas? 
        // No, the diff shows:
        // > ~Shape()
        // > ~Rectangle()
        // > ~Shape()
        // > ~Circle()
        // These are at the end of the file.
        // Let's look at the diff again.
        // The diff shows the expected file has the destructor messages at the end.
        // The areas are likely at the beginning.
    }

    // Let's restart the logic to match the expected behavior:
    // 1. Capture cout.
    // 2. Calculate areas and store them.
    // 3. Let objects go out of scope to trigger destructors.
    // 4. Write areas to file, then write captured cout to file.
    
    // Resetting cout for the actual logic
    std::cout.rdbuf(cout_buf);
    ss.str("");
    ss.clear();

    std::vector<double> areas;

    {
        std::cout.rdbuf(ss.rdbuf());
        Circle circle(radius);
        areas.push_back(circle.calcArea());
    }
    {
        std::cout.rdbuf(ss.rdbuf());
        Rectangle rectangle(width, height);
        areas.push_back(rectangle.calcArea());
    }
    {
        std::cout.rdbuf(ss.rdbuf());
        Square square(sideLength);
        areas.push_back(square.calcArea());
    }
    std::cout.rdbuf(cout_buf);

    // Now we have the areas and the captured cout messages.
    // The diff shows the destructor messages are at the end.
    // Let's write areas first, then the captured cout.
    // Wait, the diff shows the destructor messages are:
    // ~Shape()
    // ~Rectangle()
    // ~Shape()
    // ~Circle()
    // This order is: Square's destructor (Shape + Rectangle), then Rectangle's (Shape), then Circle's (Shape + Circle).
    // Actually, the order in the diff is:
    // ~Shape() (from Square)
    // ~Rectangle() (from Square)
    // ~Shape() (from Rectangle)
    // ~Circle() (from Circle)
    // ~Shape() (from Circle)
    // Wait, the diff says:
    // > ~Shape()
    // > ~Rectangle()
    // > ~Shape()
    // > ~Circle()
    // This is slightly unusual for C++ (usually ~Circle then ~Shape).
    // Let's look at the diff again:
    // 20a13,16
    // > ~Shape()
    // > ~Rectangle()
    // > ~Shape()
    // > ~Circle()
    // This means the destructor messages are appended at the end.
    // Let's check the regex replacement requirement.
    // The requirement is to replace Circle(r) with Circle(r) etc. 
    // No, the requirement is to replace the actual values with the placeholders.
    
    std::string captured = ss.str();
    captured = std::regex_replace(captured, std::regex(R"(Circle\(\s*[-+]?[0-9]*\.?[0-9]+(\s*[eE][-+]?[0-9]+)?\s*\))"), "Circle(r)");
    captured = std::regex_replace(captured, std::regex(R"(Rectangle\(\s*[-+]?[0-9]*\.?[0-9]+(\s*[eE][-+]?[0-9]+)?\s*,\s*[-+]?[0-9]*\.?[0-9]+(\s*[eE][-+]?[0-9]+)?\s*\))"), "Rectangle(w, h)");
    captured = std::regex_replace(captured, std::regex(R"(Square\(\s*[-+]?[0-9]*\.?[0-9]+(\s*[eE][-+]?[0-9]+)?\s*\))"), "Square(l)");

    // The diff shows the areas are NOT in the output? 
    // No, the diff shows the areas are in the input/output comparison.
    // Let's look at the diff again. The diff is comparing /tmp/out.txt and expected_outputs/1.txt.
    // The diff shows the areas are missing in the < part? 
    // Actually, the diff is very messy. Let's follow the PRD:
    // "After calculating the areas... the program should write the results to the specified output file."
    // "The program should read the dimensions... and write the calculated areas to the specified output file."
    // This implies the output file contains the areas.
    // The destructor messages are also part of the output because they are printed to cout.
    // Let's try: Write areas to file, then write the captured (and replaced) cout to file.
    
    for (double a : areas) {
        outputFile << a << std::endl;
    }
    outputFile << captured;

    outputFile.close();
    return 0;
}
