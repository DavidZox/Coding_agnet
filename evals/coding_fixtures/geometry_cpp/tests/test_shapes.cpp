#include <gtest/gtest.h>

#include <cmath>
#include <stdexcept>

#include "geometry/circle.hpp"
#include "geometry/rectangle.hpp"

using geometry::Circle;
using geometry::Rectangle;

TEST(CircleTest, Area) {
    Circle c(2.0);
    EXPECT_NEAR(c.area(), M_PI * 4.0, 1e-9);
    EXPECT_EQ(c.name(), "circle");
}

TEST(CircleTest, RejectsNonPositiveRadius) {
    EXPECT_THROW(Circle(0.0), std::invalid_argument);
    EXPECT_THROW(Circle(-1.0), std::invalid_argument);
}

TEST(RectangleTest, Area) {
    Rectangle r(3.0, 4.0);
    EXPECT_DOUBLE_EQ(r.area(), 12.0);
    EXPECT_EQ(r.name(), "rect");
}

TEST(RectangleTest, RejectsNonPositiveSides) {
    EXPECT_THROW(Rectangle(0.0, 1.0), std::invalid_argument);
    EXPECT_THROW(Rectangle(1.0, -2.0), std::invalid_argument);
}
