#ifndef QUEUE_HPP
#define QUEUE_HPP

template<typename T>
struct Node {
    T data;
    Node* next;
    Node(const T& d) : data(d), next(nullptr) {}
};

template<typename T>
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

    void push(const T& data) {
        Node<T>* newNode = new Node<T>(data);
        if (_rear == nullptr) {
            _front = _rear = newNode;
            return;
        }
        _rear->next = newNode;
        _rear = newNode;
    }

    T pop() {
        if (empty()) {
            return T();
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
            return T();
        }
        return _front->data;
    }

    bool empty() const {
        return _front == nullptr;
    }
};

#endif
