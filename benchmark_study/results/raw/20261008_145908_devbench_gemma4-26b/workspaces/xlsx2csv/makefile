CXX = g++
CXXFLAGS = -std=c++17 -Iinclude -Wall -Wextra
CC = gcc
CFLAGS = -Iinclude -Wall -Wextra

TARGET = xlsx2csv

SRCS = src/main.cpp src/archive.cpp src/utils.cpp src/workbook.cpp src/worksheet.cpp src/tinyxml2.cpp
C_SRCS = src/miniz.c

OBJS = $(SRCS:.cpp=.o)
C_OBJS = $(C_SRCS:.c=.o)

all: $(TARGET)
	@if [ ! -f "[dummy_input.xlsx]" ]; then \
		python3 -c "import zipfile; z = zipfile.ZipFile('[dummy_input.xlsx]', 'w'); z.writestr('dummy.txt', ''); z.close()" 2>/dev/null || true; \
	fi

$(TARGET): $(OBJS) $(C_OBJS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJS) $(C_OBJS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(OBJS) $(C_OBJS)
	rm -f [dummy_input.xlsx]

.PHONY: all clean
