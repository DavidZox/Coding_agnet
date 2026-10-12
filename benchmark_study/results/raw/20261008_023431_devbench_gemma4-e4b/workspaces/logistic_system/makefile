# Variables
CXX = g++
CXXFLAGS = -std=c++17 -Iinclude
SRCDIR = src
INCDIR = include
OBJS = $(SRCDIR)/account.o $(SRCDIR)/expressage.o $(SRCDIR)/logistics.o $(SRCDIR)/main.o
TARGET = logistics

# Default target
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp $(INCDIR)/*.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(SRCDIR)/main.o: $(SRCDIR)/main.cpp $(INCDIR)/*.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET)
