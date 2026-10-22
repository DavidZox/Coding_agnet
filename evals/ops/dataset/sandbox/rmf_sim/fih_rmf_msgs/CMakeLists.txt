cmake_minimum_required(VERSION 3.8)
project(fih_rmf_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/AllocatorCommand.msg"
  "msg/CurrentState.msg"
  "msg/HandshakeState.msg"
  "msg/RobotState.msg"
  "msg/Sequence.msg"
  "msg/TaskExecutionFinished.msg"
)

ament_package()
