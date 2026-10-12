CC = gcc
CXX = g++
CFLAGS ?= -std=c11 -Wall -Wextra -g -MMD -MP -Iinclude
CXXFLAGS ?= -std=c++17 -Wall -g -MMD -MP -Iinclude
BUILD := build

LIB_SRCS := $(filter-out src/main.c,$(wildcard src/*.c))
LIB_OBJS := $(patsubst src/%.c,$(BUILD)/%.o,$(LIB_SRCS))
TEST_SRCS := $(wildcard tests/*.cpp)
TEST_OBJS := $(patsubst tests/%.cpp,$(BUILD)/tests/%.o,$(TEST_SRCS))

.PHONY: all test clean

all: $(BUILD)/movavg

$(BUILD)/movavg: $(BUILD)/main.o $(LIB_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ -lm

$(BUILD)/%.o: src/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD)/tests/%.o: tests/%.cpp | $(BUILD)
	@mkdir -p $(BUILD)/tests
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(BUILD)/run_tests: $(TEST_OBJS) $(LIB_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ -lgtest -lgtest_main -pthread -lm

test: $(BUILD)/run_tests
	./$(BUILD)/run_tests

$(BUILD):
	@mkdir -p $(BUILD)

clean:
	$(RM) -r $(BUILD)

-include $(wildcard $(BUILD)/*.d $(BUILD)/tests/*.d)
