CC = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = -lsqlite3
TARGET = UMM

SRC_DIR = src
INCLUDE_DIR = include
BUILD_DIR = .

SRCS = $(SRC_DIR)/main.cpp \
       $(SRC_DIR)/people_management.cpp \
       $(SRC_DIR)/utils.cpp

OBJS = $(patsubst $(SRC_DIR)/%.cpp, obj/%.o, $(SRCS))

.PHONY: all clean run test

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(OBJS) -o $(TARGET) $(LDFLAGS)

obj/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p obj
	$(CC) $(CXXFLAGS) -c $< -o $@

clean:
	rm -rf obj $(TARGET)

run: $(TARGET)
	./$(TARGET)

# Makefile for testing (as per instructions, this is provided/assumed to exist)
# We define a target that mimics the structure for testing compilation,
# assuming the test executable name is consistent.
makefile_test: unit_testing.o
	$(CC) unit_testing.o -o test_runner $(LDFLAGS)

unit_testing.o: tests/unit_testing.cpp
	@mkdir -p tests
	$(CC) $(CXXFLAGS) -c $< -o $@

acceptance_testing.o: tests/acceptance_testing.py
	# Assuming Python test runner compilation/execution is handled separately or mocked here
	# For C++ compilation context, we only compile the C++ parts.
	@echo "Skipping Python test compilation in Makefile"
