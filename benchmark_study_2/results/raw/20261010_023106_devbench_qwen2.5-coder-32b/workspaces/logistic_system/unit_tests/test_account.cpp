#include <gtest/gtest.h>
#include "account.h"

TEST(AccountNodeTest, ConstructorTest) {
    AccountNode account("test_id", "test_pwd", "TestUser", "1234567890", 100.0, "TestAddress", authority::normal_user);
    EXPECT_EQ(account.getId(), "test_id");
    EXPECT_EQ(account.getPassword(), "test_pwd");
    EXPECT_EQ(account.getName(), "TestUser");
    EXPECT_EQ(account.getPhone(), "1234567890");
    EXPECT_EQ(account.getMoney(), 100.0);
    EXPECT_EQ(account.getAddress(), "TestAddress");
    EXPECT_EQ(account.getType(), authority::normal_user);
}

TEST(AccountNodeTest, SetPasswordTest) {
    AccountNode account;
    account.setPassword("new_pwd");
    EXPECT_EQ(account.getPassword(), "new_pwd");
}

TEST(AccountNodeTest, AddMoneyTest) {
    AccountNode account;
    account.addMoney(0, 100.0);
    EXPECT_EQ(account.getMoney(), 100.0);
    account.addMoney(0, 50.0);
    EXPECT_EQ(account.getMoney(), 150.0);
}

TEST(AccountNodeTest, SetMoneyTest) {
    AccountNode account;
    account.setMoney(200.0);
    EXPECT_EQ(account.getMoney(), 200.0);
}
