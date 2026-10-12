# define the C++ compiler to use
CC = g++

# define any compile-time flags
CFLAGS = -Wall -g -std=c++17

# define any directories containing header files other than /usr/include
INCLUDES = -I include/

# define any libraries to link into executable:
LIBS = -lsqlite3

# define the C++ source files
SRCS = src/main.cpp src/people_management.cpp src/utils.cpp

# define the C++ object files 
OBJS = $(SRCS:.cpp=.o)

# defines the executable file 
TARGET = UMM

.PHONY: clean all

all: $(TARGET)
	@echo Program has been compiled

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) $(INCLUDES) -o $(TARGET) $(OBJS) $(LIBS)

%.o: %.cpp
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

clean:
	$(RM) $(OBJS) $(TARGET)
