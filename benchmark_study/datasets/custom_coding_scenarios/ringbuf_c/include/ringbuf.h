#ifndef RINGBUF_H
#define RINGBUF_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 固定容量的環形緩衝區：滿了再放會蓋掉最舊的元素。 */
typedef struct {
    double *data;
    size_t capacity;
    size_t head;   /* 下一個要寫入的位置 */
    size_t count;  /* 目前的元素個數 */
} RingBuf;

/* 配置容量為 capacity 的緩衝區；capacity 為 0 或記憶體不足時回傳 false。 */
bool rb_init(RingBuf *rb, size_t capacity);
void rb_free(RingBuf *rb);

/* 放入一個值（滿了就蓋掉最舊的）。 */
void rb_push(RingBuf *rb, double value);

/* 取出最舊的值放到 *out；空的時回傳 false。 */
bool rb_pop(RingBuf *rb, double *out);

size_t rb_size(const RingBuf *rb);
bool rb_is_full(const RingBuf *rb);

/* 目前所有元素的平均；空的時回傳 0。 */
double rb_mean(const RingBuf *rb);

#ifdef __cplusplus
}
#endif

#endif /* RINGBUF_H */
