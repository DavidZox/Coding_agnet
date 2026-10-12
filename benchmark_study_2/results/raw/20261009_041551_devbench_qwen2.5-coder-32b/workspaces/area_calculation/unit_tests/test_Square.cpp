#include <gtest/gtest.h>
#include "Square.hpp"

TEST(SquareTest, ConstructorAndDestructor) {
    testing::internal::CaptureStdout();
    Square square(5.0);
    std::string output = testing::internal::GetCapturedStdout();
    // Ignore Shape's constructor output
    size_t pos = output.find("Rectangle(5, 5)\nSquare(5)\n");
    if (pos != std::string::npos) {
        output = output.substr(pos);
    }
    EXPECT_EQ(output, "Rectangle(5, 5)\nSquare(5)\n");

    testing::internal::CaptureStdout();
    square.~Square();
    output = testing::internal::GetCapturedStdout();
    // Ignore Shape's destructor output
    pos = output.find("~Square()\n~Rectangle()\n");
    if (pos != std::string::npos) {
        output = output.substr(pos, output.find("~Shape()\n") - pos);
    }
    EXPECT_EQ(output, "~Square()\n~Rectangle()\n");
}

TEST(SquareTest, CalcArea) {
    Square square(5.0);
    EXPECT_DOUBLE_EQ(square.calcArea(), 25.0);
}
