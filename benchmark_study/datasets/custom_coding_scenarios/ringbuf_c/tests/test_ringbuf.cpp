#include <gtest/gtest.h>

#include "ringbuf.h"

class RingBufTest : public ::testing::Test {
protected:
    void SetUp() override { ASSERT_TRUE(rb_init(&rb, 3)); }
    void TearDown() override { rb_free(&rb); }
    RingBuf rb;
};

TEST(RingBufInit, RejectsZeroCapacity) {
    RingBuf rb;
    EXPECT_FALSE(rb_init(&rb, 0));
}

TEST_F(RingBufTest, PushAndPopInOrder) {
    rb_push(&rb, 1.0);
    rb_push(&rb, 2.0);
    double v = 0;
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(v, 1.0);
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(v, 2.0);
    EXPECT_FALSE(rb_pop(&rb, &v));
}

TEST_F(RingBufTest, OverwritesOldestWhenFull) {
    for (double x : {1.0, 2.0, 3.0, 4.0}) {
        rb_push(&rb, x);
    }
    EXPECT_TRUE(rb_is_full(&rb));
    EXPECT_EQ(rb_size(&rb), 3u);
    double v = 0;
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(v, 2.0);
}

TEST_F(RingBufTest, MeanOfFirstValues) {
    rb_push(&rb, 2.0);
    rb_push(&rb, 4.0);
    EXPECT_DOUBLE_EQ(rb_mean(&rb), 3.0);
}
