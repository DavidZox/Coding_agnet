# gcov
COVFLAGS = -fprofile-arcs -ftest-coverage

# Variables
CXX = g++
CC = gcc   # Adding a variable for the C compiler
CXXFLAGS = -std=c++17 -Iinclude
CFLAGS = -Iinclude  # Flags for C compilation
SRCDIR = src
INCDIR = include
OBJS = $(SRCDIR)/main.o $(SRCDIR)/account.o $(SRCDIR)/expressage.o $(SRCDIR)/logistics.o
TARGET = logistics

# Default target
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -o $@ $^ -lgcov 

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp $(INCDIR)/%.h
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -c -o $@ $<

$(SRCDIR)/main.o: $(SRCDIR)/main.cpp
	$(CXX) $(CXXFLAGS) $(COVFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET) src/*.o
