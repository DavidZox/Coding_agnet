CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = -lsqlite3

SRC_DIR = src
INC_DIR = include
OBJ_DIR = obj

SRCS = $(SRC_DIR)/main.cpp $(SRC_DIR)/people_management.cpp $(SRC_DIR)/utils.cpp
OBJS = $(OBJ_DIR)/main.o $(OBJ_DIR)/people_management.o $(OBJ_DIR)/utils.o

TARGET = UMM

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(OBJS) -o $(TARGET) $(LDFLAGS)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJ_DIR) $(TARGET) database.sqlite3

.PHONY: all clean
