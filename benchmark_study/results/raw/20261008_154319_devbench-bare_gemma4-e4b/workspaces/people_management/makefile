CC = g++
CFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = -lsqlite3

# Source files
SRC_DIR = src
OBJ_DIR = obj
BIN_DIR = bin

# List of source files
SRCS = $(SRC_DIR)/main.cpp \
       $(SRC_DIR)/people_management.cpp \
       $(SRC_DIR)/utils.cpp

# List of object files
OBJS = $(patsubst $(SRC_DIR)/%.cpp, $(OBJ_DIR)/%.o, $(SRCS))

# Target executable name (based on makefile_test)
TARGET = UMM

.PHONY: all clean run

all: $(BIN_DIR)/$(TARGET)

$(BIN_DIR)/$(TARGET): $(OBJS)
	@mkdir -p $(BIN_DIR)
	$(CC) $(CFLAGS) $^ -o $@ $(LDFLAGS)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p $(OBJ_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJ_DIR) $(BIN_DIR)

run: $(BIN_DIR)/$(TARGET)
	@echo "--- Running UMM ---"
	@echo "Usage: ./$(TARGET) <command> <target> [options...]"
	@echo "Example: ./$(TARGET) add person -name \"John Doe\" -age 20 -school 1 -type 1"
	@echo "Example: ./$(TARGET) search person -type 1"
	@echo "Example: ./$(TARGET) mentor assign -student 1 -mentor 2"
	@echo "-------------------"
	# Example execution (can be modified for testing)
	./$(BIN_DIR)/$(TARGET) help
