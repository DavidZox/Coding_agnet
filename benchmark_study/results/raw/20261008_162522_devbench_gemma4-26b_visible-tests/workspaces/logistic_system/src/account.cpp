#include "account.h"
#include <iomanip>

AccountNode::AccountNode() 
    : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(user) {}

AccountNode::AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type)
    : id(id), password(password), name(name), phone(phone), money(money), address(address), type(type) {}

std::ostream& operator<<(std::ostream& os, const AccountNode& node) {
    os << "AccountId: " << node.id << "\n";
    os << "UserName: " << node.name << "\n";
    os << "UserPhone: " << node.phone << "\n";
    os << "Money: " << node.money << "\n";
    os << "Address: " << node.address << "\n";
    
    os << "UserType: ";
    if (node.type == root) {
        os << "root";
    } else if (node.type == admin) {
        os << "admin";
    } else {
        os << "normal user";
    }
    os << "\n";
    
    return os;
}
