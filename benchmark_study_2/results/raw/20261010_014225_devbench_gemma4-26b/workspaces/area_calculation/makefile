# gcov
COVFLAGS = -fprofile-arcs -ftest-coverage

# Variables
CXX = g++
CXXFLAGS = -std=c++17 -Iinclude
CFLAGS = -Iinclude  # Flags for C compilation
SRCDIR = src
INCDIR = include
INCDIR_TEST = .
OBJS = $(SRCDIR)/main.o $(SRCDIR)/Shape.o $(SRCDIR)/Rectangle.o
TARGET = area_calculation

# Default target
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -o $@ $^ -lgcov 

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -c -o $@ $<

$(SRCDIR)/main.o: $(SRCDIR)/main.cpp
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET) src/*.gcda src/*.gcno src/*.gcov *.gcda *.gcno *.gcov

.PHONY: all clean
