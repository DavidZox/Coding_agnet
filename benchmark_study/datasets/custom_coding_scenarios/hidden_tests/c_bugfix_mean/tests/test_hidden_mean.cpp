#include <gtest/gtest.h>

#include "ringbuf.h"

TEST(HiddenMean, AfterWrapAndPop) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 3));
    for (double x : {1.0, 2.0, 3.0, 4.0}) {
        rb_push(&rb, x);
    }
    double v = 0;
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(rb_mean(&rb), 3.5);
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(rb_mean(&rb), 4.0);
    rb_free(&rb);
}

TEST(HiddenMean, FullAfterWrap) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 3));
    for (double x : {1.0, 2.0, 3.0, 4.0, 5.0}) {
        rb_push(&rb, x);
    }
    EXPECT_DOUBLE_EQ(rb_mean(&rb), 4.0);
    rb_free(&rb);
}
