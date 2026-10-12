# Variables
CXX = g++
CC = gcc   # Adding a variable for the C compiler
CXXFLAGS = -std=c++17 -Iinclude
CFLAGS = -Iinclude  # Flags for C compilation
SRCDIR = src
INCDIR = include
INCDIR_TEST = .
OBJS = $(SRCDIR)/main.o $(SRCDIR)/account.o  $(SRCDIR)/expressage.o $(SRCDIR)/logistics.o
TARGET = logistics

TEST_DIR = ./unit_tests
TEST_OBJS = ${TEST_DIR}/test_account.o ${TEST_DIR}/test_expressage.o ${TEST_DIR}/test_logistics.o
TEST_TARGET = run_tests
GTEST_LIB = -lgtest -lgtest_main -pthread

# Default target
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(OBJS)

$(SRCDIR)/%.o: $(SRCDIR)/%.cpp $(INCDIR)/%.h
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(SRCDIR)/main.o: $(SRCDIR)/main.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

# Test targets

PROD_OBJS = $(filter-out $(SRCDIR)/main.o, $(OBJS))

$(TEST_TARGET): $(PROD_OBJS) $(TEST_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(GTEST_LIB)

$(TEST_DIR)/%.o: $(TEST_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

test: $(TEST_TARGET)
	./$(TEST_TARGET)

clean:
	rm -f $(OBJS) $(TARGET) $(TEST_TARGET) $(TEST_OBJS) src/*.gcda src/*.gcno src/*.gcov *.gcda *.gcno *.gcov

.PHONY: all clean
