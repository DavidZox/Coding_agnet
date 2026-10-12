CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = 
TARGET = xlsx2csv

# Source files
SRCDIR = src
OBJDIR = obj
SOURCES = $(wildcard $(SRCDIR)/*.cpp)
OBJECTS = $(patsubst $(SRCDIR)/%.cpp, $(OBJDIR)/%.o, $(SOURCES))

# External dependencies (as per architecture_design.md)
# miniz.c and tinyxml2.cpp are provided/assumed to be in src/
# We must compile them too.
MINIZ_SRC = $(SRCDIR)/miniz.c
TINYXML2_SRC = $(SRCDIR)/tinyxml2.cpp
ALL_SOURCES = $(SOURCES) $(MINIZ_SRC) $(TINYXML2_SRC)
ALL_OBJECTS = $(patsubst $(SRCDIR)/%.cpp, $(OBJDIR)/%.o, $(SOURCES)) $(OBJDIR)/miniz.o $(OBJDIR)/tinyxml2.o

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJECTS) $(OBJDIR)/miniz.o $(OBJDIR)/tinyxml2.o
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDFLAGS)

# Rule for compiling C++ source files
$(OBJDIR)/%.o: $(SRCDIR)/%.cpp
	@mkdir -p $(OBJDIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Rule for compiling C files (miniz.c)
$(OBJDIR)/miniz.o: $(SRCDIR)/miniz.c
	@mkdir -p $(OBJDIR)
	$(CXX) -c $< -o $@

# Rule for compiling tinyxml2.cpp (assuming it's a C++ file)
$(OBJDIR)/tinyxml2.o: $(SRCDIR)/tinyxml2.cpp
	@mkdir -p $(OBJDIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJDIR) $(TARGET)
