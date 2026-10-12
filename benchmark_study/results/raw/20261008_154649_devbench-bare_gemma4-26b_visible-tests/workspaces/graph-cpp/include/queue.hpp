#ifndef QUEUE_HPP
#define QUEUE_HPP

#include <stdexcept>

template <typename T>
struct Node {
    T data;
    Node* next;
    Node(const T& val) : data(val), next(nullptr) {}
};

template <typename T>
class Queue {
private:
    Node<T>* _front;
    Node<T>* _rear;

public:
    Queue() : _front(nullptr), _rear(nullptr) {}

    ~Queue() {
        while (!empty()) {
            pop();
        }
    }

    bool empty() const {
        return _front == nullptr;
    }

    void push(const T& data) {
        Node<T>* newNode = new Node<T>(data);
        if (empty()) {
            _front = _rear = newNode;
        } else {
            _rear->next = newNode;
            _rear = newNode;
        }
    }

    T front() {
        if (empty()) {
            throw std::out_of_range("Queue is empty");
        }
        return _front->data;
    }

    T pop() {
        if (empty()) {
            throw std::out_of_range("Queue is empty");
        }
        Node<T>* temp = _front;
        T data = temp->data;
        _front = _front->next;
        if (_front == nullptr) {
            _rear = nullptr;
        }
        delete temp;
        return data;
    }
};

#endif
