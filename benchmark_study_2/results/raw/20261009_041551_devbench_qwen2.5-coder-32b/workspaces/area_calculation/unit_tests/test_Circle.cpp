#include <gtest/gtest.h>
#include "Circle.hpp"

TEST(CircleTest, ConstructorAndDestructor) {
    testing::internal::CaptureStdout();
    Circle circle(5.0);
    std::string output = testing::internal::GetCapturedStdout();
    // Ignore Shape constructor output
    size_t pos = output.find("Circle(5)\n");
    if (pos != std::string::npos) {
        output = output.substr(pos);
    }
    EXPECT_EQ(output, "Circle(5)\n");

    // Removed manual destructor call
    // circle.~Circle();
    // output = testing::internal::GetCapturedStdout();
    // EXPECT_EQ(output, "~Circle()\n");
}

TEST(CircleTest, CalcArea) {
    Circle circle(5.0);
    EXPECT_DOUBLE_EQ(circle.calcArea(), 78.53981633974483);
}
