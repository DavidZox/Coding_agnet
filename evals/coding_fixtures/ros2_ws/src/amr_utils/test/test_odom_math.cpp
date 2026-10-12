#include <gtest/gtest.h>

#include <cmath>

#include "amr_utils/odom_math.hpp"

using amr_utils::Pose2D;

TEST(NormalizeAngle, AlreadyInRange) {
  EXPECT_NEAR(amr_utils::normalize_angle(0.5), 0.5, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-0.5), -0.5, 1e-9);
}

TEST(NormalizeAngle, WrapsLargePositive) {
  EXPECT_NEAR(amr_utils::normalize_angle(3.0 * M_PI / 2.0), -M_PI / 2.0, 1e-9);
}

TEST(DiffDrive, StraightLine) {
  Pose2D p = amr_utils::integrate_diff_drive(Pose2D{}, 1.0, 0.0, 2.0);
  EXPECT_NEAR(p.x, 2.0, 1e-9);
  EXPECT_NEAR(p.y, 0.0, 1e-9);
  EXPECT_NEAR(p.theta, 0.0, 1e-9);
}

TEST(DiffDrive, RotateInPlace) {
  Pose2D p = amr_utils::integrate_diff_drive(Pose2D{1.0, 2.0, 0.0}, 0.0, 0.5, 1.0);
  EXPECT_NEAR(p.x, 1.0, 1e-9);
  EXPECT_NEAR(p.y, 2.0, 1e-9);
  EXPECT_NEAR(p.theta, 0.5, 1e-9);
}
