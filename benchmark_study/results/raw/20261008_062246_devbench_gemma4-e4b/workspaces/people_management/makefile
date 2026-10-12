CC = g++
CXXFLAGS = -std=c++17 -Wall -Wextra
LDFLAGS = -lsqlite3
TARGET = UMM

SRC_DIR = src
INC_DIR = include
BUILD_DIR = .

SRCS = $(SRC_DIR)/main.cpp \
       $(SRC_DIR)/people_management.cpp \
       $(SRC_DIR)/utils.cpp

OBJS = $(patsubst $(SRC_DIR)/%.cpp, $(BUILD_DIR)/%.o, $(SRCS))

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CXXFLAGS) $(OBJS) -o $(TARGET) $(LDFLAGS)

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.cpp
	$(CC) $(CXXFLAGS) -c $< -o $@ -I$(INC_DIR)

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
