#include <gtest/gtest.h>

#include "ringbuf.h"

TEST(HiddenPeek, OldestWithoutRemoving) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 3));
    double v = 0;
    EXPECT_FALSE(rb_peek_oldest(&rb, &v));
    for (double x : {1.0, 2.0, 3.0, 4.0}) {
        rb_push(&rb, x);
    }
    ASSERT_TRUE(rb_peek_oldest(&rb, &v));
    EXPECT_DOUBLE_EQ(v, 2.0);
    EXPECT_EQ(rb_size(&rb), 3u);
    rb_free(&rb);
}

TEST(HiddenClear, EmptiesAndKeepsWorking) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 2));
    rb_push(&rb, 1.0);
    rb_push(&rb, 2.0);
    rb_clear(&rb);
    EXPECT_EQ(rb_size(&rb), 0u);
    double v = 0;
    EXPECT_FALSE(rb_pop(&rb, &v));
    rb_push(&rb, 5.0);
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(v, 5.0);
    rb_free(&rb);
}
