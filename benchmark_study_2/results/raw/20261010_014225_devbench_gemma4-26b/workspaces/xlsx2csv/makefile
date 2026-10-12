CXX = g++
CXXFLAGS = -std=c++17 -Iinclude -Wall -Wextra
CC = gcc
CFLAGS = -Iinclude -Wall -Wextra

TARGET = xlsx2csv

SRCS = src/workbook.cpp src/worksheet.cpp src/archive.cpp src/utils.cpp src/main.cpp src/tinyxml2.cpp
C_SRCS = src/miniz.c

OBJS = $(SRCS:.cpp=.o)
C_OBJS = $(C_SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS) $(C_OBJS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJS) $(C_OBJS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(OBJS) $(C_OBJS)

.PHONY: all clean
