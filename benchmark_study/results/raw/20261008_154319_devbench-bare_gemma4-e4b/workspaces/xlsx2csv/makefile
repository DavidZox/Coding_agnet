CC = g++
CFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = 
TARGET = xlsx2csv

# Source files
SRC_DIR = src
OBJ_DIR = obj
SOURCES = $(wildcard $(SRC_DIR)/*.cpp)
OBJECTS = $(patsubst $(SRC_DIR)/%.cpp, $(OBJ_DIR)/%.o, $(SOURCES))

# External dependencies (as per architecture_design.md)
# miniz.c and tinyxml2.cpp are provided and must be compiled.
EXTERNAL_SOURCES = $(SRC_DIR)/miniz.c $(SRC_DIR)/tinyxml2.cpp
EXTERNAL_OBJECTS = $(patsubst $(SRC_DIR)/%.c, $(OBJ_DIR)/%.o, $(EXTERNAL_SOURCES))

# All object files
ALL_OBJECTS = $(OBJECTS) $(EXTERNAL_OBJECTS)

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(ALL_OBJECTS)
	$(CC) $(CFLAGS) $(ALL_OBJECTS) -o $@ $(LDFLAGS)

# Rule for compiling source files
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p $(OBJ_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

# Rule for compiling external C files (miniz.c)
$(OBJ_DIR)/miniz.o: $(SRC_DIR)/miniz.c
	@mkdir -p $(OBJ_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

# Rule for compiling external C++ files (tinyxml2.cpp)
$(OBJ_DIR)/tinyxml2.o: $(SRC_DIR)/tinyxml2.cpp
	@mkdir -p $(OBJ_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJ_DIR) $(TARGET)
