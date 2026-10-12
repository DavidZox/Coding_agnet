#ifndef STACK_HPP
#define STACK_HPP

#include <stdexcept>
#include <iostream>

template <typename T>
class Stack {
private:
    static const int DEFAULT_SIZE = 10;
    T* _array;
    int size;
    int capacity;

public:
    // Constructor
    Stack() : capacity(DEFAULT_SIZE), size(0) {
        _array = new T[capacity];
    }

    // Destructor
    ~Stack() {
        delete[] _array;
    }

    // Copy constructor and assignment operator (Rule of Three/Five)
    Stack(const Stack& other) : capacity(other.capacity), size(other.size) {
        _array = new T[capacity];
        for (int i = 0; i < size; ++i) {
            _array[i] = other._array[i];
        }
    }

    Stack& operator=(const Stack& other) {
        if (this != &other) {
            delete[] _array;
            capacity = other.capacity;
            size = other.size;
            _array = new T[capacity];
            for (int i = 0; i < size; ++i) {
                _array[i] = other._array[i];
            }
        }
        return *this;
    }

    // Push operation
    void push(const T& data) {
        if (size == capacity) {
            // Resize logic (doubling capacity)
            int new_capacity = capacity * 2;
            T* new_array = new T[new_capacity];
            for (int i = 0; i < size; ++i) {
                new_array[i] = _array[i];
            }
            for (int i = 0; i < 1; ++i) {
                new_array[size + i] = data;
            }
            delete[] _array;
            _array = new_array;
            capacity = new_capacity;
            size++;
        } else {
            _array[size] = data;
            size++;
        }
    }

    // Pop operation
    T pop() {
        if (empty()) {
            throw std::out_of_range("Stack::pop(): Stack is empty");
        }
        T data = _array[size - 1];
        size--;
        return data;
    }

    // Top operation
    T top() const {
        if (empty()) {
            throw std::out_of_range("Stack::top(): Stack is empty");
        }
        return _array[size - 1];
    }

    // Empty check
    bool empty() const {
        return size == 0;
    }

    // Getters (optional but useful for debugging/verification)
    int getSize() const { return size; }
    int getCapacity() const { return capacity; }
};

#endif // STACK_HPP
