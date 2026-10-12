CC = g++
CXXFLAGS = -std=c++17 -Wall -Wextra
LDFLAGS =

TARGET = graph
SRCDIR = src
INCDIR = include
SOURCES = src/main.cpp
OBJECTS = src/main.o

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(CXXFLAGS) $(OBJECTS) -o $(TARGET) $(LDFLAGS)

src/main.o: src/main.cpp
	$(CC) $(CXXFLAGS) -c $< -o $@ -I$(INCDIR)

clean:
	rm -f $(TARGET) $(OBJECTS)
