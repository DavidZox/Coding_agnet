#include <gtest/gtest.h>

#include <stdexcept>

#include "geometry/registry.hpp"
#include "geometry/triangle.hpp"

using namespace geometry;

TEST(HiddenTriangle, HeronArea) {
    Triangle t(3.0, 4.0, 5.0);
    EXPECT_NEAR(t.area(), 6.0, 1e-9);
    EXPECT_EQ(t.name(), "triangle");
}

TEST(HiddenTriangle, RejectsInvalidSides) {
    EXPECT_THROW(Triangle(1.0, 2.0, 3.0), std::invalid_argument);
    EXPECT_THROW(Triangle(-1.0, 2.0, 2.0), std::invalid_argument);
    EXPECT_THROW(Triangle(1.0, 1.0, 5.0), std::invalid_argument);
}

TEST(HiddenTriangle, ParseShape) {
    auto s = parse_shape("triangle 3 4 5");
    EXPECT_EQ(s->name(), "triangle");
    EXPECT_NEAR(s->area(), 6.0, 1e-9);
    EXPECT_THROW(parse_shape("triangle 3 4"), std::invalid_argument);
}
