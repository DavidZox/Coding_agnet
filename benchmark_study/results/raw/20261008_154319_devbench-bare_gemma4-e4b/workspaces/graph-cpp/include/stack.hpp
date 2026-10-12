#ifndef STACK_HPP
#define STACK_HPP

template <typename T>
class Stack {
private:
    static const int DEFAULT_SIZE = 10;
    T* _array;
    int size;
    int capacity;

public:
    // Constructor
    Stack(int capacity = DEFAULT_SIZE) : capacity(capacity), size(0) {
        _array = new T[capacity];
    }

    // Destructor to free memory
    ~Stack() {
        delete[] _array;
    }

    // Push an element onto the top of the stack
    void push(const T& data) {
        if (size == capacity) {
            // In a real-world scenario, we might resize, but based on UML, we assume fixed capacity or handle overflow.
            // For this implementation, we'll throw or handle based on typical fixed-size array behavior.
            // Since the UML doesn't specify resizing, we'll throw an exception on overflow.
            throw std::overflow_error("Stack overflow");
        }
        _array[size] = data;
        size++;
    }

    // Retrieve the top element of the stack without removing it
    T top() const {
        if (empty()) {
            throw std::out_of_range("Stack is empty");
        }
        return _array[size - 1];
    }

    // Remove and return the top element of the stack
    T pop() {
        if (empty()) {
            throw std::out_of_range("Stack is empty");
        }
        size--;
        T data = _array[size];
        return data;
    }

    // Check if the stack is empty
    bool empty() const {
        return size == 0;
    }
};

#endif // STACK_HPP
