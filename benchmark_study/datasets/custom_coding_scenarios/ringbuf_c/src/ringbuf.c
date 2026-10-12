#include "ringbuf.h"

#include <stdlib.h>

bool rb_init(RingBuf *rb, size_t capacity) {
    if (capacity == 0) {
        return false;
    }
    rb->data = malloc(capacity * sizeof(double));
    if (rb->data == NULL) {
        return false;
    }
    rb->capacity = capacity;
    rb->head = 0;
    rb->count = 0;
    return true;
}

void rb_free(RingBuf *rb) {
    free(rb->data);
    rb->data = NULL;
    rb->capacity = rb->head = rb->count = 0;
}

void rb_push(RingBuf *rb, double value) {
    rb->data[rb->head] = value;
    rb->head = (rb->head + 1) % rb->capacity;
    if (rb->count < rb->capacity) {
        rb->count++;
    }
}

bool rb_pop(RingBuf *rb, double *out) {
    if (rb->count == 0) {
        return false;
    }
    size_t tail = (rb->head + rb->capacity - rb->count) % rb->capacity;
    *out = rb->data[tail];
    rb->count--;
    return true;
}

size_t rb_size(const RingBuf *rb) { return rb->count; }

bool rb_is_full(const RingBuf *rb) { return rb->count == rb->capacity; }

double rb_mean(const RingBuf *rb) {
    if (rb->count == 0) {
        return 0.0;
    }
    double sum = 0.0;
    for (size_t i = 0; i < rb->count; i++) {
        sum += rb->data[i];
    }
    return sum / (double)rb->count;
}
