TARGET = xlsx2csv

CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = -lz

SOURCES = src/archive.cpp src/utils.cpp src/worksheet.cpp src/workbook.cpp src/main.cpp src/miniz.c src/tinyxml2.cpp
OBJECTS = $(SOURCES:.cpp=.o) $(SOURCES:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJECTS) $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.o: %.c
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(OBJECTS)
