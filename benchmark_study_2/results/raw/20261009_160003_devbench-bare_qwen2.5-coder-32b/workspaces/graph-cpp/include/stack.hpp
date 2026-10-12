#ifndef STACK_HPP
#define STACK_HPP

#include <iostream>

template <typename T>
class Stack {
private:
    static const int DEFAULT_SIZE = 10;
    T* _array;
    int size;
    int capacity;

    void resize() {
        capacity *= 2;
        T* newArray = new T[capacity];
        for (int i = 0; i < size; ++i) {
            newArray[i] = _array[i];
        }
        delete[] _array;
        _array = newArray;
    }

public:
    Stack() : _array(new T[DEFAULT_SIZE]), size(0), capacity(DEFAULT_SIZE) {}

    ~Stack() {
        delete[] _array;
    }

    void push(const T& data) {
        if (size == capacity) {
            resize();
        }
        _array[size++] = data;
    }

    T top() {
        if (empty()) {
            throw std::out_of_range("Stack is empty");
        }
        return _array[size - 1];
    }

    void pop() {
        if (empty()) {
            throw std::out_of_range("Stack is empty");
        }
        --size;
    }

    bool empty() {
        return size == 0;
    }
};

#endif // STACK_HPP
