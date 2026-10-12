#ifndef STACK_HPP
#define STACK_HPP

#include <stdexcept>

template <typename T>
class Stack {
private:
    const int DEFAULT_SIZE = 10;
    T* _array;
    int size;
    int capacity;

    void resize(int new_capacity) {
        T* new_array = new T[new_capacity];
        for (int i = 0; i < size; ++i) {
            new_array[i] = _array[i];
        }
        delete[] _array;
        _array = new_array;
        capacity = new_capacity;
    }

public:
    Stack() : size(0), capacity(DEFAULT_SIZE) {
        _array = new T[capacity];
    }

    ~Stack() {
        delete[] _array;
    }

    void push(const T& data) {
        if (size == capacity) {
            resize(capacity * 2);
        }
        _array[size++] = data;
    }

    T top() const {
        if (empty()) {
            throw std::runtime_error("Stack is empty");
        }
        return _array[size - 1];
    }

    void pop() {
        if (empty()) {
            throw std::runtime_error("Stack is empty");
        }
        size--;
    }

    bool empty() const {
        return size == 0;
    }
};

#endif
