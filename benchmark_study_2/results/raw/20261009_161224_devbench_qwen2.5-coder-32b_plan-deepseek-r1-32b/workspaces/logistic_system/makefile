# Compiler
CXX = g++

# Compiler flags
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -Iinclude

# Source files
SRCS = src/main.cpp src/account.cpp src/expressage.cpp src/logistics.cpp

# Object files
OBJS = $(SRCS:.cpp=.o)

# Target executable
TARGET = logistics_management_system

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
