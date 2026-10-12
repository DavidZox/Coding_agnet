#include "Circle.hpp"
#include "Rectangle.h"
#include "Square.hpp"
#include <iostream>
#include <fstream>
#include <vector>
#include <memory>

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

    double r, w, h, l;
    if (!(inputFile >> r >> w >> h >> l)) {
        return 1;
    }
    inputFile.close();

    std::vector<std::unique_ptr<Shape>> shapes;
    shapes.push_back(std::make_unique<Circle>(r));
    shapes.push_back(std::make_unique<Rectangle>(w, h));
    shapes.push_back(std::make_unique<Square>(l));

    std::ofstream outputFile(outputFileName);
    if (!outputFile.is_open()) {
        return 1;
    }

    for (const auto& shape : shapes) {
        outputFile << shape->calcArea() << std::endl;
    }
    outputFile.close();

    return 0;
}
