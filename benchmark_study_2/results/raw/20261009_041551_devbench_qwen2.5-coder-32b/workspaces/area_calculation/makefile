CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 --coverage
TARGET = main

SRCDIR = src
INCDIR = include

SRCS = $(SRCDIR)/main.cpp $(SRCDIR)/Shape.cpp $(SRCDIR)/Rectangle.cpp $(SRCDIR)/Circle.cpp $(SRCDIR)/Square.cpp
OBJS = $(SRCS:.cpp=.o)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ -I$(INCDIR)

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@ -I$(INCDIR)

clean:
	rm -f $(OBJS) $(TARGET)
