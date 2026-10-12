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

    void resize(int newCapacity) {
        T* newArray = new T[newCapacity];
        for (int i = 0; i < size; ++i) {
            newArray[i] = _array[i];
        }
        delete[] _array;
        _array = newArray;
        capacity = newCapacity;
    }

public:
    Stack() : _array(new T[DEFAULT_SIZE]), size(0), capacity(DEFAULT_SIZE) {}

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
            throw std::out_of_range("Stack is empty");
        }
        return _array[size - 1];
    }

    void pop() {
        if (empty()) {
            throw std::out_of_range("Stack is empty");
        }
        --size;
        if (size > 0 && size == capacity / 4) {
            resize(capacity / 2);
        }
    }

    bool empty() const {
        return size == 0;
    }
};

#endif // STACK_HPP
