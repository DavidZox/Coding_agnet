#include <gtest/gtest.h>

#include <cmath>
#include <memory>

#include "geometry/circle.hpp"
#include "geometry/rectangle.hpp"
#include "geometry/shape.hpp"

using namespace geometry;

TEST(HiddenPerimeter, Circle) { EXPECT_NEAR(Circle(1.5).perimeter(), 2 * M_PI * 1.5, 1e-9); }

TEST(HiddenPerimeter, Rectangle) { EXPECT_DOUBLE_EQ(Rectangle(2.0, 3.5).perimeter(), 11.0); }

TEST(HiddenPerimeter, ThroughBasePointer) {
    std::unique_ptr<Shape> s = std::make_unique<Rectangle>(1.0, 1.0);
    EXPECT_DOUBLE_EQ(s->perimeter(), 4.0);
}
