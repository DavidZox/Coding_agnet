#include "Rectangle.h"

Rectangle::Rectangle() : width(0), height(0) {
    std::cout << "Rectangle()" << std::endl;
}

Rectangle::Rectangle(double _w, double _h) : width(_w), height(_h) {
    std::cout << "Rectangle(" << width << ", " << height << ")" << std::endl;
}

Rectangle::~Rectangle() {
    std::cout << "~Rectangle()" << std::endl;
}

double Rectangle::calcArea() {
    return width * height;
}
