CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS = 
TARGET = xlsx2csv

# Source files
SRCS = src/main.cpp \
       src/utils.cpp \
       src/archive.cpp \
       src/workbook.cpp \
       src/worksheet.cpp \
       src/miniz.c \
       src/tinyxml2.cpp

# Object files
OBJS = $(SRCS:.cpp=.o)
OBJS += src/miniz.o src/tinyxml2.o

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(OBJS) -o $@ $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.o: %.c
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(OBJS)

# Target for testing (as per instructions, this should match the structure)
makefile_test: $(TARGET)
