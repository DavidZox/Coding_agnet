#ifndef QUEUE_HPP
#define QUEUE_HPP

#include <iostream>

namespace custom {

template <typename T>
class Node {
public:
    T data;
    Node* next;

    Node(const T& data) : data(data), next(nullptr) {}
};

template <typename T>
class Queue {
private:
    Node<T>* _rear;
    Node<T>* _front;

public:
    Queue() : _rear(nullptr), _front(nullptr) {}

    ~Queue() {
        while (!empty()) {
            pop();
        }
    }

    void push(const T& data) {
        Node<T>* newNode = new Node<T>(data);
        if (_rear == nullptr) {
            _front = _rear = newNode;
        } else {
            _rear->next = newNode;
            _rear = newNode;
        }
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

    T front() {
        if (empty()) {
            throw std::out_of_range("Queue is empty");
        }
        return _front->data;
    }

    bool empty() {
        return _front == nullptr;
    }
};

} // namespace custom

#endif // QUEUE_HPP
