CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra
LDFLAGS =

TARGET = shape_calculator
SRCDIR = src
INCDIR = include

SOURCES = $(SRCDIR)/main.cpp \
          $(SRCDIR)/Shape.cpp \
          $(SRCDIR)/Rectangle.cpp \
          $(SRCDIR)/Circle.cpp \
          $(SRCDIR)/Square.cpp

OBJECTS = $(SOURCES:.cpp=.o)

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) -o $(TARGET) $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -I$(INCDIR) -c $< -o $@

clean:
	rm -f $(OBJECTS) $(TARGET)

.PHONY: all clean
