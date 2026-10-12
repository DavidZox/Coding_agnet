CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = 

# Target executable name
TARGET = xlsx2csv

# Source files
SRCS = src/main.cpp \
       src/archive.cpp \
       src/utils.cpp \
       src/workbook.cpp \
       src/worksheet.cpp \
       src/tinyxml2.cpp \
       src/miniz.c

# Object files
OBJS = $(SRCS:.cpp=.o)
OBJS := $(OBJS:.c=.o)

# Default target
all: $(TARGET)

# Link the executable
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJS) $(LDFLAGS)

# Compile C++ files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Compile C files
%.o: %.c
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean target
clean:
	rm -f $(TARGET) $(OBJS)

.PHONY: all clean
