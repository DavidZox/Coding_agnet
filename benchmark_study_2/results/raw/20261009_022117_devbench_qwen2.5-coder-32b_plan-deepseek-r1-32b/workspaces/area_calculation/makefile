# Compiler
CXX = g++

# Compiler flags
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -Iinclude

# Source files
SRCS = src/main.cpp src/Rectangle.cpp src/Shape.cpp src/Circle.cpp src/Square.cpp

# Object files
OBJS = $(SRCS:.cpp=.o)

# Executable file
TARGET = main

# Default target
all: $(TARGET)

# Link object files to create the executable
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

# Compile source files to object files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean up build files
clean:
	rm -f $(OBJS) $(TARGET)
