#include <gtest/gtest.h>

#include "geometry/registry.hpp"

using namespace geometry;

TEST(HiddenTotal, SumsAllShapes) {
    auto shapes = parse_shapes("rect 1 2\nrect 3 1\n");
    EXPECT_DOUBLE_EQ(total_area(shapes), 5.0);
}

TEST(HiddenTotal, SingleShape) {
    auto shapes = parse_shapes("rect 2 2\n");
    EXPECT_DOUBLE_EQ(total_area(shapes), 4.0);
}

TEST(HiddenTotal, Empty) {
    ShapeList none;
    EXPECT_DOUBLE_EQ(total_area(none), 0.0);
}
