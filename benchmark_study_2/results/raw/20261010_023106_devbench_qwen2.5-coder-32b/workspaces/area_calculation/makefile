CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra
TARGET = main

SRCDIR = src
INCDIR = include

SRCS = $(wildcard $(SRCDIR)/*.cpp)
OBJS = $(SRCS:$(SRCDIR)/%.cpp=$(SRCDIR)/%.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ -I$(INCDIR)

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@ -I$(INCDIR)

clean:
	rm -f $(OBJS) $(TARGET)
