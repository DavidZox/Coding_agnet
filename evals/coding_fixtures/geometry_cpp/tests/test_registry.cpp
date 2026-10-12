#include <gtest/gtest.h>

#include <stdexcept>

#include "geometry/registry.hpp"

using namespace geometry;

TEST(RegistryTest, ParsesCircleAndRect) {
    auto c = parse_shape("circle 1");
    EXPECT_EQ(c->name(), "circle");
    auto r = parse_shape("  rect 2 5 ");
    EXPECT_DOUBLE_EQ(r->area(), 10.0);
}

TEST(RegistryTest, RejectsUnknownShape) {
    EXPECT_THROW(parse_shape("hexagon 3"), std::invalid_argument);
    EXPECT_THROW(parse_shape("rect 2"), std::invalid_argument);
}

TEST(RegistryTest, SkipsBlankAndCommentLines) {
    auto shapes = parse_shapes("# shapes\nrect 1 2\n\n   \nrect 3 1\n");
    ASSERT_EQ(shapes.size(), 2u);
}
