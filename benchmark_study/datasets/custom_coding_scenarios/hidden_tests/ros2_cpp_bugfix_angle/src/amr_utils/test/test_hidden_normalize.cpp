#include <gtest/gtest.h>

#include <cmath>

#include "amr_utils/odom_math.hpp"

TEST(HiddenNormalize, NegativeWraps) {
  EXPECT_NEAR(amr_utils::normalize_angle(-3.0 * M_PI / 2.0), M_PI / 2.0, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-4.0), -4.0 + 2.0 * M_PI, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-7.0), -7.0 + 2.0 * M_PI, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-10.0), -10.0 + 4.0 * M_PI, 1e-9);
}

TEST(HiddenNormalize, PositiveStillWorks) {
  EXPECT_NEAR(amr_utils::normalize_angle(7.0), 7.0 - 2.0 * M_PI, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(0.5), 0.5, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-0.5), -0.5, 1e-9);
}

TEST(HiddenNormalize, RotateBackwardsKeepsRange) {
  amr_utils::Pose2D p;
  for (int i = 0; i < 40; ++i) {
    p = amr_utils::integrate_diff_drive(p, 0.0, -1.0, 0.1);
  }
  EXPECT_GT(p.theta, -M_PI);
  EXPECT_LE(p.theta, M_PI);
  EXPECT_NEAR(p.theta, -4.0 + 2.0 * M_PI, 1e-6);
}
