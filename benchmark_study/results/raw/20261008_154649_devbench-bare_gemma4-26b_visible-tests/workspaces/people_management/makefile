CXX = g++
CXXFLAGS = -std=c++17 -Wall -Iinclude
LDFLAGS = -lsqlite3

SRC_DIR = src
OBJ_DIR = obj
INCLUDE_DIR = include

# According to architecture design and requirements
TARGET = UMM

# Source files
SRCS = $(SRC_DIR)/main.cpp \
       $(SRC_DIR)/people_management.cpp \
       $(SRC_DIR)/utils.cpp

# Object files
OBJS = $(SRCS:$(SRC_DIR)/%.cpp=$(OBJ_DIR)/%.o)

# Default target
all: $(TARGET)

# Link the executable
$(TARGET): $(OBJS)
	$(CXX) $(OBJS) -o $(TARGET) $(LDFLAGS)

# Compile source files to object files
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean up build artifacts
clean:
	rm -rf $(OBJ_DIR) $(TARGET) database.sqlite3

.PHONY: all clean
