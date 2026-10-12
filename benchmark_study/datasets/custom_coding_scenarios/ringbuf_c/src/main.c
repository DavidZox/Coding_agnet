#include <stdio.h>
#include <stdlib.h>

#include "ringbuf.h"

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: movavg <N>\n");
        return 2;
    }
    long n = strtol(argv[1], NULL, 10);
    RingBuf rb;
    if (n <= 0 || !rb_init(&rb, (size_t)n)) {
        fprintf(stderr, "N must be a positive integer\n");
        return 2;
    }
    double x;
    while (scanf("%lf", &x) == 1) {
        rb_push(&rb, x);
        printf("%.2f\n", rb_mean(&rb));
    }
    rb_free(&rb);
    return 0;
}
