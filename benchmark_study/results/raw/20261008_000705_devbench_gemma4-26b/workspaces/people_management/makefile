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
MAIN = UMM

.PHONY: clean

all: $(MAIN)
	@echo Program has been compiled

$(MAIN): $(OBJS)
	$(CC) $(CFLAGS) $(INCLUDES) -o $(MAIN) $(OBJS) $(LIBS)

%.o: %.cpp
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

clean:
	$(RM) src/*.o $(MAIN)
