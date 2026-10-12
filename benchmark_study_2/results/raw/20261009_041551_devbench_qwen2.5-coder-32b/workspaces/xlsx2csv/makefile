# Compiler and flags
CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2

# Source files
SRCS = src/archive.cpp src/utils.cpp src/worksheet.cpp src/workbook.cpp src/main.cpp src/miniz.c src/tinyxml2.cpp

# Object files
OBJS = $(SRCS:.cpp=.o) $(SRCS:.c=.o)

# Executable file
TARGET = xlsx2csv

# Include directories
INCS = -Iinclude

# Default target
all: $(TARGET)

# Link object files to create the executable
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $(INCS) -o $(TARGET) $(OBJS)

# Compile C++ source files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) $(INCS) -c $< -o $@

# Compile C source files
%.o: %.c
	$(CXX) $(CXXFLAGS) $(INCS) -c $< -o $@

# Clean up build files
clean:
	rm -f $(OBJS) $(TARGET)
