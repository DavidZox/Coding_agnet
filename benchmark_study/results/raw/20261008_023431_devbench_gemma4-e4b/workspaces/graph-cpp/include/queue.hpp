#ifndef QUEUE_HPP
#define QUEUE_HPP

#include <iostream>
#include <stdexcept>

template <typename T>
class Queue {
private:
    struct Node {
        T data;
        Node* next;
        Node(const T& val) : data(val), next(nullptr) {}
    };

    Node* _front;
    Node* _rear;

public:
    Queue() : _front(nullptr), _rear(nullptr) {}

    // Destructor to free memory
    ~Queue() {
        Node* current = _front;
        while (current != nullptr) {
            Node* next = current->next;
            delete current;
            current = next;
        }
    }

    // Push operation
    void push(const T& data) {
        Node* newNode = new Node(data);
        if (empty()) {
            _front = newNode;
            _rear = newNode;
        } else {
            _rear->next = newNode;
            _rear = newNode;
        }
    }

    // Pop operation
    T pop() {
        if (empty()) {
            throw std::out_of_range("Queue is empty");
        }
        Node* temp = _front;
        T data = temp->data;
        _front = _front->next;
        if (_front == nullptr) {
            _rear = nullptr;
        } else {
            _rear->next = nullptr; // Ensure the new rear points to null if it was the last element
        }
        delete temp;
        return data;
    }

    // Front operation
    T front() {
        if (empty()) {
            throw std::out_of_range("Queue is empty");
        }
        return _front->data;
    }

    // Empty check
    bool empty() const {
        return _front == nullptr;
    }
};

#endif // QUEUE_HPP
