#ifndef QUEUE_HPP
#define QUEUE_HPP

template <typename T>
class Queue {
private:
    struct Node {
        Node* next;
        T data;
    };
    Node* _rear;
    Node* _front;

public:
    Queue() : _rear(nullptr), _front(nullptr) {}

    // Destructor to free memory
    ~Queue() {
        Node* current = _front;
        while (current != nullptr) {
            Node* next = current->next;
            delete current;
            current = next;
        }
    }

    // Push an element to the back of the queue
    void push(const T& data) {
        Node* newNode = new Node{nullptr, data};
        if (empty()) {
            _front = newNode;
            _rear = newNode;
        } else {
            _rear->next = newNode;
            _rear = newNode;
        }
    }

    // Remove and return the front element of the queue
    T pop() {
        if (empty()) {
            throw std::out_of_range("Queue is empty");
        }
        Node* temp = _front;
        T data = temp->data;
        _front = _front->next;
        if (_front == nullptr) {
            _rear = nullptr;
        }
        delete temp;
        return data;
    }

    // Return the front element of the queue without removing it
    T front() {
        if (empty()) {
            throw std::out_of_range("Queue is empty");
        }
        return _front->data;
    }

    // Check if the queue is empty
    bool empty() const {
        return _front == nullptr;
    }
};

#endif // QUEUE_HPP
