# Compiler
CXX = g++

# Compiler flags
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -Iinclude

# Source files
SRCS = src/Shape.cpp src/Rectangle.cpp src/Square.cpp src/main.cpp

# Object files
OBJS = $(SRCS:.cpp=.o)

# Executable file
TARGET = main

# Default rule
all: $(TARGET)

# Rule to link object files into the executable
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

# Rule to compile source files into object files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean rule
clean:
	rm -f $(OBJS) $(TARGET)
