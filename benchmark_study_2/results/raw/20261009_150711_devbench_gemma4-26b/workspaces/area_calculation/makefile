# Variables
CXX = g++
CXXFLAGS = -std=c++17 -Iinclude
SRCDIR = src
INCDIR = include
OBJS = $(SRCDIR)/main.o $(SRCDIR)/Shape.o $(SRCDIR)/Rectangle.o
TARGET = area_calculation

# Default target
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(SRCDIR)/Shape.o: $(SRCDIR)/Shape.cpp $(INCDIR)/Shape.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(SRCDIR)/Rectangle.o: $(SRCDIR)/Rectangle.cpp $(INCDIR)/Rectangle.h $(INCDIR)/Shape.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(SRCDIR)/main.o: $(SRCDIR)/main.cpp $(INCDIR)/Circle.hpp $(INCDIR)/Rectangle.h $(INCDIR)/Square.hpp $(INCDIR)/Shape.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
