# 沙盒用的「調度系統」容器：ROS 2 Jazzy＋fih_rmf_msgs（從 amr_base 複製的訊息定義）＋rmf_sim（假的 orchestrtor／distribute／機器人／web_console／manual_trigger）。
# 工作區放在 /workspaces/amr_base（跟使用者的開發容器一樣），harness 的 ROS2 技能會自動 source 它的 install/setup.bash。
FROM ros:jazzy-ros-base
SHELL ["/bin/bash", "-c"]
COPY fih_rmf_msgs /workspaces/amr_base/src/fih_rmf_msgs
RUN source /opt/ros/jazzy/setup.bash && cd /workspaces/amr_base && colcon build --packages-select fih_rmf_msgs && rm -rf build log
# 沙盒跟正式系統隔離：另一個 ROS_DOMAIN_ID；容器都在 Docker-in-Docker 裡面的網路（多播出不了沙盒），
# 所以沙盒裡的容器之間可以互相探索（SUBNET），但碰不到主機與機器人的網路
ENV ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
COPY rmf_sim.py /opt/rmf_sim/rmf_sim.py
COPY default_config.json /opt/rmf_sim/config.json
RUN echo 'source /opt/ros/jazzy/setup.bash && source /workspaces/amr_base/install/setup.bash' >> /root/.bashrc
CMD ["bash", "-c", "source /opt/ros/jazzy/setup.bash && source /workspaces/amr_base/install/setup.bash && exec python3 -u /opt/rmf_sim/rmf_sim.py --config /opt/rmf_sim/config.json"]
