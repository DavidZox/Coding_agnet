#include "account.h"

AccountNode::AccountNode() : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(authority::normal_user) {}

AccountNode::AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type)
    : id(id), password(password), name(name), phone(phone), money(money), address(address), type(type) {}

std::ostream& operator<<(std::ostream& os, const AccountNode& account) {
    os << account.id << " " << account.password << " " << account.name << " " << account.phone << " " 
       << account.money << " " << account.address << " " << static_cast<int>(account.type);
    return os;
}
