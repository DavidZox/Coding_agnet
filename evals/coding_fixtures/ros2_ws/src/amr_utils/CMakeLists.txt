cmake_minimum_required(VERSION 3.8)
project(amr_utils)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)

add_library(odom_math src/odom_math.cpp)
target_include_directories(odom_math PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

add_executable(odom_node src/odom_node.cpp)
target_link_libraries(odom_node odom_math)
ament_target_dependencies(odom_node rclcpp geometry_msgs nav_msgs)

install(TARGETS odom_math odom_node
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_odom_math test/test_odom_math.cpp)
  target_link_libraries(test_odom_math odom_math)
  ament_add_gtest(test_odom_node test/test_odom_node.cpp)
  target_link_libraries(test_odom_node odom_math)
  ament_target_dependencies(test_odom_node rclcpp nav_msgs)
endif()

ament_package()
