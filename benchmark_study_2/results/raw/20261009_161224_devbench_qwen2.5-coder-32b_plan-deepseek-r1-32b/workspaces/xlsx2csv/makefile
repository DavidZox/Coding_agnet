CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = -lz

TARGET = xlsx2csv

SRCS = src/archive.cpp src/utils.cpp src/worksheet.cpp src/workbook.cpp src/main.cpp src/miniz.c src/tinyxml2.cpp
OBJS = $(SRCS:.cpp=.o) $(SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJS) $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.o: %.c
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)
