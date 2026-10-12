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

public:
    Stack() : size(0), capacity(DEFAULT_SIZE) {
        _array = new T[capacity];
    }

    ~Stack() {
        delete[] _array;
    }

    bool empty() const {
        return size == 0;
    }

    void push(const T& data) {
        if (size == capacity) {
            int newCapacity = capacity * 2;
            T* newArray = new T[newCapacity];
            for (int i = 0; i < size; ++i) {
                newArray[i] = _array[i];
            }
            delete[] _array;
            _array = newArray;
            capacity = newCapacity;
        }
        _array[size++] = data;
    }

    T top() const {
        if (empty()) {
            throw std::out_of_range("stack underflow");
        }
        return _array[size - 1];
    }

    void pop() {
        if (empty()) {
            throw std::out_of_range("stack underflow");
        }
        size--;
    }
};

#endif
