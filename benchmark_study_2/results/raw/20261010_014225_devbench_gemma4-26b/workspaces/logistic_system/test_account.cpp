#include "include/account.h"
#include <iostream>
#include <string>
#include <cassert>

int main() {
    // Test default constructor
    AccountNode acc1;
    // Since we don't have the implementation of operator<< yet, 
    // we just test the getters for default values if possible.
    // However, the default constructor in account.h doesn't initialize id, password, etc.
    // So we focus on the parameterized constructor.

    // Test parameterized constructor
    AccountNode acc2("test_id", "test_pwd", "TestUser", "1234567890", 100.0, "TestAddress", admin);
    
    assert(acc2.getId() == "test_id");
    assert(acc2.getPassword() == "test_pwd");
    assert(acc2.getName() == "TestUser");
    assert(acc2.getPhone() == "1234567890");
    assert(acc2.getMoney() == 100.0);
    assert(acc2.getAddress() == "TestAddress");
    assert(acc2.getType() == admin);

    // Test setters
    acc2.setPassword("new_pwd");
    assert(acc2.getPassword() == "new_pwd");

    acc2.setMoney(200.5);
    assert(acc2.getMoney() == 200.5);

    std::cout << "AccountNode tests passed!" << std::endl;
    return 0;
}
