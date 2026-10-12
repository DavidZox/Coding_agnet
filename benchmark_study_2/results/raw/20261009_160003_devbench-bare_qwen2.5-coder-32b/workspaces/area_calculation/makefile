CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2
TARGET = main

SRCS = src/main.cpp src/Rectangle.cpp src/Shape.cpp
OBJS = $(SRCS:.cpp=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
