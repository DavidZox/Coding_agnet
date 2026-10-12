#include "amr_utils/odom_math.hpp"

#include <cmath>

namespace amr_utils {

double normalize_angle(double angle) {
  return std::fmod(angle + M_PI, 2.0 * M_PI) - M_PI;
}

Pose2D integrate_diff_drive(const Pose2D& pose, double v, double w, double dt) {
  // Midpoint integration: use the heading halfway through the step.
  const double mid = pose.theta + 0.5 * w * dt;
  Pose2D out;
  out.x = pose.x + v * dt * std::cos(mid);
  out.y = pose.y + v * dt * std::sin(mid);
  out.theta = normalize_angle(pose.theta + w * dt);
  return out;
}

}  // namespace amr_utils
