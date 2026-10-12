#include <gtest/gtest.h>
#include "Rectangle.h"

TEST(RectangleTest, ConstructorAndDestructor) {
    testing::internal::CaptureStdout();
    Rectangle rectangle(4.0, 5.0);
    std::string output = testing::internal::GetCapturedStdout();
    EXPECT_EQ(output, "Shape()\nRectangle(4, 5)\n");

    testing::internal::CaptureStdout();
    rectangle.~Rectangle();
    output = testing::internal::GetCapturedStdout();
    EXPECT_EQ(output, "~Rectangle()\n~Shape()\n");
}

TEST(RectangleTest, CalcArea) {
    Rectangle rectangle(4.0, 5.0);
    EXPECT_DOUBLE_EQ(rectangle.calcArea(), 20.0);
}
