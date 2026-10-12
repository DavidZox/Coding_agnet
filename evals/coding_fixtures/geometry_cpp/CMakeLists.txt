cmake_minimum_required(VERSION 3.16)
project(geometry CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# src/ 底下的 .cpp 都編進 geometry 函式庫（新增檔案不用改這裡）
file(GLOB GEOMETRY_SOURCES CONFIGURE_DEPENDS src/*.cpp)
add_library(geometry ${GEOMETRY_SOURCES})
target_include_directories(geometry PUBLIC include)

add_executable(geometry_cli app/main.cpp)
target_link_libraries(geometry_cli PRIVATE geometry)

enable_testing()
find_package(GTest REQUIRED)
file(GLOB TEST_SOURCES CONFIGURE_DEPENDS tests/*.cpp)
add_executable(geometry_tests ${TEST_SOURCES})
target_link_libraries(geometry_tests PRIVATE geometry GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(geometry_tests)
