# Variables
CXX = g++
CC = gcc
CXXFLAGS = -std=c++17 -Iinclude
CFLAGS = -Iinclude
SRCDIR = src
INCDIR = include
OBJS = $(SRCDIR)/archive.o $(SRCDIR)/miniz.c.o $(SRCDIR)/tinyxml2.o $(SRCDIR)/utils.o $(SRCDIR)/workbook.o $(SRCDIR)/worksheet.o $(SRCDIR)/main.o
TARGET = xlsx2csv

# Default target
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp $(INCDIR)/%.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(SRCDIR)/miniz.c.o: $(SRCDIR)/miniz.c
	$(CC) $(CFLAGS) -c -o $@ $<

$(SRCDIR)/tinyxml2.o: $(SRCDIR)/tinyxml2.cpp $(INCDIR)/tinyxml2.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
