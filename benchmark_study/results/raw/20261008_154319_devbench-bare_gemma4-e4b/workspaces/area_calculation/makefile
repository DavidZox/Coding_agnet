CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -pedantic
LDFLAGS =

# Source files
SRC_DIR = src
INC_DIR = include
SRCS = $(SRC_DIR)/main.cpp \
       $(SRC_DIR)/Shape.cpp \
       $(SRC_DIR)/Rectangle.cpp

# Object files
OBJS = $(patsubst $(SRC_DIR)/%.cpp, obj/%.o, $(SRCS))

# Executable name (based on makefile_test target)
TARGET = devbench

.PHONY: all clean run

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $(OBJS) -o $@ $(LDFLAGS)

obj/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p obj
	$(CXX) $(CXXFLAGS) -I$(INC_DIR) -c $< -o $@

clean:
	rm -rf obj $(TARGET)

run: $(TARGET)
	./$(TARGET) input.txt output.txt
