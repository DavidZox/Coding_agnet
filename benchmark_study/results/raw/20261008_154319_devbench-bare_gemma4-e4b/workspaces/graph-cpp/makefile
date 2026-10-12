CC = g++
CFLAGS = -std=c++17 -Wall -Wextra -pedantic
LDFLAGS = 
TARGET = graph

SRC_DIR = src
INC_DIR = include

SRCS = $(SRC_DIR)/main.cpp
OBJS = $(patsubst $(SRC_DIR)/%.cpp, obj/%.o, $(SRCS))

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) -o $(TARGET) $(LDFLAGS)

obj/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p obj
	$(CC) $(CFLAGS) -I$(INC_DIR) -c $< -o $@

clean:
	rm -rf obj $(TARGET)
