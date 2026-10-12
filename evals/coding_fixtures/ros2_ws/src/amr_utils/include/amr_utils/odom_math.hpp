#pragma once

namespace amr_utils {

struct Pose2D {
  double x = 0.0;
  double y = 0.0;
  double theta = 0.0;  // rad, kept in (-pi, pi]
};

// Wrap an angle into (-pi, pi].
double normalize_angle(double angle);

// Dead reckoning for a differential-drive base: linear speed v (m/s), angular speed w (rad/s), time step dt (s).
Pose2D integrate_diff_drive(const Pose2D& pose, double v, double w, double dt);

}  // namespace amr_utils
