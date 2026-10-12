CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra
LDFLAGS =

TARGET = graph
SRCDIR = src
INCDIR = include
# Explicitly list source files since wildcard might fail in some environments
OBJECTS = obj/main.o

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) -o $(TARGET) $(LDFLAGS)

obj/main.o: $(SRCDIR)/main.cpp
	@mkdir -p obj
	$(CXX) $(CXXFLAGS) -I$(INCDIR) -c $< -o $@

clean:
	rm -rf obj $(TARGET)
