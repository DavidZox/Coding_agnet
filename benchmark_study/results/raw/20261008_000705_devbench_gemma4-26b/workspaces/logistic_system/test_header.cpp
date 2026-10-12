#include "include/expressage.h"
#include <iostream>
#include <string>

int main() {
    ExpressageNode e;
    ExpressageNode e2("KD00000001", "user1", "user2", "2020-01-01", "NULL", "Remark", false);
    
    std::cout << "Test ExpressageNode construction and output:" << std::endl;
    std::cout << e2 << std::endl;
    
    e2.Sign("2020-01-02");
    std::cout << "After Sign:" << std::endl;
    std::cout << e2 << std::endl;

    return 0;
}
