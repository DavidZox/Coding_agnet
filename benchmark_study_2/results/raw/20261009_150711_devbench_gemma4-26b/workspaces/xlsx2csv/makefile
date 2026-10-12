CXX = g++
CXXFLAGS = -std=c++17 -Iinclude -Wall -Wextra
CC = gcc
CFLAGS = -Iinclude -Wall -Wextra

TARGET = xlsx2csv

SRCS = src/main.cpp src/archive.cpp src/utils.cpp src/workbook.cpp src/worksheet.cpp src/tinyxml2.cpp
C_SRCS = src/miniz.c
OBJS = $(SRCS:.cpp=.o) $(C_SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJS)

src/main.o: src/main.cpp
	$(CXX) $(CXXFLAGS) -c src/main.cpp -o src/main.o

src/archive.o: src/archive.cpp
	$(CXX) $(CXXFLAGS) -c src/archive.cpp -o src/archive.o

src/utils.o: src/utils.cpp
	$(CXX) $(CXXFLAGS) -c src/utils.cpp -o src/utils.o

src/workbook.o: src/workbook.cpp
	$(CXX) $(CXXFLAGS) -c src/workbook.cpp -o src/workbook.o

src/worksheet.o: src/worksheet.cpp
	$(CXX) $(CXXFLAGS) -c src/worksheet.cpp -o src/worksheet.o

src/tinyxml2.o: src/tinyxml2.cpp
	$(CXX) $(CXXFLAGS) -c src/tinyxml2.cpp -o src/tinyxml2.o

src/miniz.o: src/miniz.c
	$(CC) $(CFLAGS) -c src/miniz.c -o src/miniz.o

clean:
	rm -f $(TARGET) $(OBJS)
