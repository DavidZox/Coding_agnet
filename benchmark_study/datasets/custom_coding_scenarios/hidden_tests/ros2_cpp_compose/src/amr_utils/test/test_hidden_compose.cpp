#include <gtest/gtest.h>

#include <cmath>

#include "amr_utils/odom_math.hpp"

using amr_utils::Pose2D;

TEST(HiddenCompose, IdentityLeft) {
  Pose2D r = amr_utils::compose(Pose2D{}, Pose2D{1.0, 2.0, 0.3});
  EXPECT_NEAR(r.x, 1.0, 1e-9);
  EXPECT_NEAR(r.y, 2.0, 1e-9);
  EXPECT_NEAR(r.theta, 0.3, 1e-9);
}

TEST(HiddenCompose, RotatedFrame) {
  Pose2D r = amr_utils::compose(Pose2D{1.0, 1.0, M_PI / 2.0}, Pose2D{2.0, 0.0, 0.0});
  EXPECT_NEAR(r.x, 1.0, 1e-9);
  EXPECT_NEAR(r.y, 3.0, 1e-9);
  EXPECT_NEAR(r.theta, M_PI / 2.0, 1e-9);
}

TEST(HiddenCompose, ThetaWraps) {
  Pose2D r = amr_utils::compose(Pose2D{0.0, 0.0, 3.0}, Pose2D{0.0, 0.0, 0.5});
  EXPECT_NEAR(r.theta, 3.5 - 2.0 * M_PI, 1e-9);
}

TEST(HiddenCompose, ConstInputs) {
  const Pose2D a{0.5, -0.5, -0.4};
  const Pose2D b{1.0, 1.0, 0.2};
  Pose2D r = amr_utils::compose(a, b);
  EXPECT_NEAR(r.x, 0.5 + std::cos(-0.4) - std::sin(-0.4), 1e-9);
  EXPECT_NEAR(r.y, -0.5 + std::sin(-0.4) + std::cos(-0.4), 1e-9);
  EXPECT_NEAR(r.theta, -0.2, 1e-9);
}
