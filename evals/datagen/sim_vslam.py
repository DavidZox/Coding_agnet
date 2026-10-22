"""VSLAM_package 的模擬（stella_vslam_ros 的 run_slam；Isaac 的雙目相機），照目錄：
- 所有輸出都在一對影像的 callback 裡：沒有影像就什麼都沒有、也沒有 Log（沒有 watchdog）。
- /run_slam/tracking_state 只在改變時發（TRANSIENT_LOCAL）；Lost 時 pose 停、keyframes 照發（不變）。
- 追蹤丟失、重定位、重置的 Log 是 spdlog（只到 stdout），/rosout 只有「Tracking state: …」、錨定與 static TF。
影像縮小成 32×18（只為了檔案小；分析程式對位元組陣列只量長度，內容不影響事實）。"""
from sim_core import Alive, Signal, header, quat_yaw

SVR = "/workspaces/amr_base/src/VSLAM_package/stella_vslam_ros/src/stella_vslam_ros.cc"


class Vslam:
    """情境：lost(t, d)（追蹤丟失 d 秒後重定位）、image_gap(t, d)（相機停 d 秒）、reset(t, d)（初始化後 5 秒內丟失 → 重新初始化）。"""

    def __init__(self, sim, rate=14.0, w=32, h=18):
        self.sim, self.rng = sim, sim.rng
        self.rate, self.w, self.h = rate, w, h
        self.cam = Alive()
        self.state = Signal("Tracking")
        self.events = []
        self.boot_t = None

    def boot(self, t):
        self.boot_t = t
        self.cam = Alive(t + 0.5)

    def lost(self, t, d):
        self.state.set(t, "Lost")
        self.state.set(t + d, "Tracking")
        self.events.append(("lost", t, d))

    def reset(self, t, d):
        self.state.set(t, "Initializing")
        self.state.set(t + d, "Tracking")
        self.events.append(("reset", t, d))

    def image_gap(self, t, d):
        self.cam.gap(t, d)
        self.events.append(("gap", t, d))

    def build(self):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        left = sim.events("/zed_camera_left/image_raw", "sensor_msgs/msg/Image")
        right = sim.events("/zed_camera_right/image_raw", "sensor_msgs/msg/Image")
        cpose = sim.events("/run_slam/camera_pose", "nav_msgs/msg/Odometry")
        rpose = sim.events("/run_slam/robot_pose", "nav_msgs/msg/Odometry")
        kf = sim.events("/run_slam/keyframes", "geometry_msgs/msg/PoseArray")
        ts = sim.onchange("/run_slam/tracking_state", "std_msgs/msg/String", latched=True)
        for s in (left, right, cpose, rpose, kf):
            s.rate = self.rate
        data = bytes(self.w * self.h * 3)
        img = lambda t, frame: {"header": header(sim, t, frame), "height": self.h, "width": self.w, "encoding": "rgb8",  # noqa: E731
                                "is_bigendian": 0, "step": self.w * 3, "data": data}
        prev, n_kf, x = None, 1, 0.0
        if self.boot_t is None:
            ts.publish(0.0011, {"data": self.state.at(0.0)})
            prev = self.state.at(0.0)
        t = (self.boot_t + 0.6) if self.boot_t is not None else rng.uniform(0, 1 / self.rate)
        while t < D:
            if self.cam.contains(t):
                left.publish(t, img(t, "zed_left_camera_frame"))
                right.publish(t + 0.0003, img(t, "zed_right_camera_frame"))
                tp = t + rng.uniform(0.03, 0.06)   # 處理一對影像的時間
                st = self.state.at(t)
                if st != prev:
                    ts.publish(tp, {"data": st})
                    sim.log(tp - 0.0002, "INFO", "run_slam", f"Tracking state: {st}", (SVR, "handle_tracking_result", 551))
                    if prev is None:
                        sim.log(tp + 0.0001, "INFO", "run_slam", "vslam_map is anchored to L_BASE_FOOTPRINT (camera zed_left_camera_frame at 0.090, 0.060, 1.290)",
                                (SVR, "update_map_anchor", 298))
                        sim.log(tp + 0.0003, "INFO", "run_slam", "Published static TF odom -> vslam_map (0.000, 0.000, 0.000, yaw 0.00 deg)",
                                (SVR, "publish_map_parent_tf", 321))
                    prev = st
                if st == "Tracking":
                    x += 0.02 + rng.gauss(0, 0.001)
                    for s, child, z in ((cpose, "zed_left_camera_link", 1.29), (rpose, "L_BASE_FOOTPRINT", 0.0)):
                        s.publish(tp + 0.0001, {"header": header(sim, t, "vslam_map"), "child_frame_id": child,
                                                "pose": {"pose": {"position": {"x": x, "y": rng.gauss(0, 0.002), "z": z}, "orientation": quat_yaw(0.0)},
                                                         "covariance": [0.0] * 36},
                                                "twist": {"twist": {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}},
                                                          "covariance": [0.0] * 36}})
                    if rng.random() < 0.05:
                        n_kf += 1
                if st != "Initializing":
                    kf.publish(tp + 0.0003, {"header": header(sim, t, "vslam_map"),
                                             "poses": [{"position": {"x": i * 0.4, "y": 0.0, "z": 1.29}, "orientation": quat_yaw(0.0)} for i in range(n_kf)]})
            t += 1 / self.rate * (1 + rng.gauss(0, 0.01))
        for kind, t0, d in self.events:
            if kind == "lost":
                sim.expect_value("/run_slam/tracking_state", t0, "Lost", key=True, what="VSLAM 追蹤丟失")
                sim.expect_value("/run_slam/tracking_state", t0 + d, "Tracking", key=True, what="VSLAM 重定位")
                sim.expect_gap("/run_slam/camera_pose", t0, d, what="pose 停止輸出")
            elif kind == "reset":
                sim.expect_value("/run_slam/tracking_state", t0, "Initializing", key=True, what="VSLAM 重新初始化")
            elif kind == "gap":
                for topic in ("/zed_camera_left/image_raw", "/run_slam/camera_pose", "/run_slam/keyframes"):
                    sim.expect_gap(topic, t0, d, key=topic.startswith("/zed"), what=f"{topic} 中斷")
        sim.expect_tags("/run_slam/tracking_state", not_=("訊息中斷", "開始或停止發布"))
        return self
