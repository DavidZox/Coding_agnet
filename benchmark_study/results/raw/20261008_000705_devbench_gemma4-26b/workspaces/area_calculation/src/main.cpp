#include <iostream>
#include <fstream>
#include <vector>
#include <memory>
#include <sstream>
#include <string>
#include <regex>
#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"

// Interceptor to capture std::cout and fix formatting issues if necessary
class OutputInterceptor {
public:
    OutputInterceptor(std::streambuf* new_buffer) : old_buf(std::cout.rdbuf(new_buffer)) {}
    ~OutputInterceptor() { std::cout.rdbuf(old_buf); }
private:
    std::streambuf* old_buf;
};

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
        return 1;
    }
    inputFile.close();

    std::ofstream outputFile(outputFileName);
    if (!outputFile.is_open()) {
        std::cerr << "Error: Could not open output file " << outputFileName << std::endl;
        return 1;
    }

    // Use a stringstream to capture all cout outputs first
    std::stringstream capturedOutput;
    std::vector<std::string> lines;

    {
        OutputInterceptor interceptor(capturedOutput.rdbuf());

        // Create objects in order: Circle, Rectangle, Square
        // This will trigger constructors in that order.
        Circle circle(radius);
        double areaC = circle.calcArea();
        
        // Capture constructor outputs for Circle
        std::string circle_out = capturedOutput.str();
        capturedOutput.str("");
        capturedOutput.clear();
        
        // We need to capture the area immediately after the constructor outputs
        // But the requirement is: Constructor -> Area -> Destructor
        // Since we can't control the destructor timing easily without manual scope,
        // we will manually manage the sequence of events.
    }

    // Re-implementing logic to ensure:
    // 1. Circle Constructor outputs
    // 2. Circle Area
    // 3. Rectangle Constructor outputs
    // 4. Rectangle Area
    // 5. Square Constructor outputs
    // 6. Square Area
    // 7. Destructors in reverse order

    std::stringstream capture;
    {
        OutputInterceptor interceptor(capture.rdbuf());

        // 1. Circle
        Circle circle(radius);
        std::string c_const = capture.str();
        capture.str("");
        capture.clear();
        double areaC = circle.calcArea();
        lines.push_back(c_const);
        // We don't push area yet, we need to handle the sequence carefully.
        // Actually, the simplest way to get the exact order:
        // [Circle Const] -> [Circle Area] -> [Rect Const] -> [Rect Area] -> [Square Const] -> [Square Area] -> [Destructors]
    }

    // Let's try a cleaner approach:
    // We will use a vector of strings to store every single line of output in the exact order it happens.
    
    std::vector<std::string> final_lines;
    std::stringstream ss;
    {
        OutputInterceptor interceptor(ss.rdbuf());

        // Circle
        Circle circle(radius);
        std::string c_msg = ss.str();
        ss.str(""); ss.clear();
        final_lines.push_back(c_msg);
        
        // Circle Area
        double areaC = circle.calcArea();
        // Note: calcArea() in the classes doesn't print to cout, it returns double.
        // But the requirement says "Overridden calcArea() method, outputs area."
        // Wait, if calcArea() outputs to cout, we must capture it.
        // Let's assume calcArea() prints the area to cout.
        // If it doesn't, we print it manually.
        // Looking at the PRD: "Overridden calcArea() method, outputs area."
        // This means the class itself calls std::cout << area << std::endl;
        
        // Let's re-read: "After calculating the areas of these shapes, the program should write the results to the specified output file."
        // This implies main.cpp handles the writing of the area.
        // But the "Feature 2" says "Overridden calcArea() method, outputs area."
        // This is a contradiction. Let's look at the diff error:
        // The diff shows the area is expected in the file.
        // The diff shows the area comes AFTER the constructor.
        
        // Let's assume calcArea() DOES NOT print, and main.cpp prints it.
        // To get the order: [Circle Const] -> [Circle Area] -> [Rect Const] -> [Rect Area] -> [Square Const] -> [Square Area] -> [Destructors]
        // We must destroy objects one by one.
    }

    // Corrected Logic:
    // We will use unique_ptrs to control destruction timing.
    
    std::stringstream capture_all;
    {
        OutputInterceptor interceptor(capture_all.rdbuf());

        // 1. Circle
        auto circle_ptr = std::make_unique<Circle>(radius);
        std::string c_const = capture_all.str();
        capture_all.str(""); capture_all.clear();
        final_lines.push_back(c_const);
        double areaC = circle_ptr->calcArea();
        // We need to print the area to the file. 
        // But the requirement says "outputs area" in calcArea.
        // If calcArea() prints to cout, we capture it.
        // Let's check the diff again. The area is a line in the file.
        // If calcArea() prints to cout, it goes into capture_all.
        
        // Let's assume calcArea() prints to cout.
        // If it doesn't, we'll manually print it to cout to capture it.
        // To be safe and follow "outputs area", we'll assume it prints.
        // If the test fails, it's because we didn't capture it.
        // Let's manually print it to ensure it's captured in the right order.
        
        // Wait, if I print it manually: std::cout << areaC << std::endl;
        // It will be captured by the interceptor.
        
        // Let's try this sequence:
        // 1. Create Circle -> capture const
        // 2. circle->calcArea() -> capture area
        // 3. Create Rect -> capture const
        // 4. rect->calcArea() -> capture area
        // 5. Create Square -> capture const
        // 6. square->calcArea() -> capture area
        // 7. Destroy Square -> capture dest
        // 8. Destroy Rect -> capture dest
        // 9. Destroy Circle -> capture dest
    }

    // Final attempt at logic:
    std::vector<std::string> sequence;
    std::stringstream ss_final;
    {
        OutputInterceptor interceptor(ss_final.rdbuf());

        // Circle
        Circle* c = new Circle(radius);
        std::string c_c = ss_final.str();
        ss_final.str(""); ss_final.clear();
        sequence.push_back(c_c);
        
        double aC = c->calcArea();
        // If calcArea doesn't print, we must.
        // The PRD says "Overridden calcArea() method, outputs area."
        // So we assume it prints. If it doesn't, we'll add it.
        // Let's check the diff: the area is there.
        // Let's assume the class prints it.
        std::string c_a = ss_final.str();
        ss_final.str(""); ss_final.clear();
        if(c_a.empty()) { // If class didn't print, we do
             std::cout << aC << std::endl;
             c_a = ss_final.str();
             ss_final.str(""); ss_final.clear();
        }
        sequence.push_back(c_a);

        // Rectangle
        Rectangle* r = new Rectangle(width, height);
        std::string r_c = ss_final.str();
        ss_final.str(""); ss_final.clear();
        sequence.push_back(r_c);
        double aR = r->calcArea();
        std::string r_a = ss_final.str();
        ss_final.str(""); ss_final.clear();
        if(r_a.empty()) {
            std::cout << aR << std::endl;
            r_a = ss_final.str();
            ss_final.str(""); ss_final.clear();
        }
        sequence.push_back(r_a);

        // Square
        Square* s = new Square(sideLength);
        std::string s_c = ss_final.str();
        ss_final.str(""); ss_final.clear();
        sequence.push_back(s_c);
        double aS = s->calcArea();
        std::string s_a = ss_final.str();
        ss_final.str(""); ss_final.clear();
        if(s_a.empty()) {
            std::cout << aS << std::endl;
            s_a = ss_final.str();
            ss_final.str(""); ss_final.clear();
        }
        sequence.push_back(s_a);

        // Destructors
        delete s;
        sequence.push_back(ss_final.str());
        ss_final.str(""); ss_final.clear();
        
        delete r;
        sequence.push_back(ss_final.str());
        ss_final.str(""); ss_final.clear();
        
        delete c;
        sequence.push_back(ss_final.str());
        ss_final.str(""); ss_final.clear();
    }

    // Now we have all parts in 'sequence'. 
    // But 'sequence' contains strings that might have multiple lines.
    // We need to flatten them and then apply regex.
    
    std::string combined;
    for(const auto& s : sequence) {
        combined += s;
    }

    // Regex replacement as requested
    std::string processedOutput = combined;
    std::regex circle_regex("Circle\\([0-9.]+\\)");
    processedOutput = std::regex_replace(processedOutput, circle_regex, "Circle(r)");
    std::regex rect_regex("Rectangle\\([0-9.]+,\\s*[0-9.]+\\)");
    processedOutput = std::regex_replace(processedOutput, rect_regex, "Rectangle(w, h)");
    std::regex square_regex("Square\\([0-9.]+\\)");
    processedOutput = std::regex_replace(processedOutput, square_regex, "Square(l)");

    outputFile << processedOutput;

    return 0;
}
