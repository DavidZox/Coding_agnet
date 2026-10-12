#include "account.h"
#include <iostream>
#include <iomanip>

std::ostream& operator<<(std::ostream& os, const AccountNode& node) {
    os << "AccountId: " << node.getId() << "\n";
    os << "UserName: " << node.getName() << "\n";
    os << "UserPhone: " << node.getPhone() << "\n";
    os << "Money: " << std::fixed << std::setprecision(2) << node.getMoney() << "\n";
    os << "Address: " << node.getAddress() << "\n";
    
    std::string typeStr;
    authority type = node.getType();
    if (type == 0) typeStr = "root";
    else if (type == 1) typeStr = "admin";
    else typeStr = "normal user";
    os << "UserType: " << typeStr << "\n";
    return os;
}
