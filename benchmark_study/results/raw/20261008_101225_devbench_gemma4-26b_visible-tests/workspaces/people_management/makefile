CXX = g++
CXXFLAGS = -std=c++17 -I. -Iinclude -Wall -Wextra
LDFLAGS = -lsqlite3

SRC = src/main.cpp src/people_management.cpp src/utils.cpp
TARGET = UMM

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(SRC) -o $(TARGET) $(LDFLAGS)

clean:
	rm -f $(TARGET)
