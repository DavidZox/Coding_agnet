#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

#include "geometry/registry.hpp"

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: geometry_cli <file>\n";
        return 2;
    }
    std::ifstream file(argv[1]);
    if (!file) {
        std::cerr << "cannot open " << argv[1] << "\n";
        return 1;
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    try {
        auto shapes = geometry::parse_shapes(buffer.str());
        std::cout << std::fixed << std::setprecision(2);
        for (const auto& s : shapes) {
            std::cout << s->name() << " " << s->area() << "\n";
        }
        std::cout << "total " << geometry::total_area(shapes) << "\n";
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
