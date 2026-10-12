# gcov
COVFLAGS = -fprofile-arcs -ftest-coverage

# Variables
CXX = g++
CXXFLAGS = -std=c++17 -Iinclude
CFLAGS = -Iinclude  # Flags for C compilation
SRCDIR = src
INCDIR = include
OBJS = $(SRCDIR)/main.o $(SRCDIR)/Shape.o $(SRCDIR)/Rectangle.o $(SRCDIR)/Circle.o $(SRCDIR)/Square.o
TARGET = area_calculation

# Default target
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -o $@ $^ -lgcov 

# Generic rule for compiling all source files
$(SRCDIR)/%.o: $(SRCDIR)/%.cpp
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -c -o $@ $<

# Rule for Circle.o (since Circle.cpp is missing in the original list but needed)
$(SRCDIR)/Circle.o: $(SRCDIR)/Circle.cpp
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET) src/*.gcda src/*.gcno src/*.gcov
.PHONY: all clean
