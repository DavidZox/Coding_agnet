#include "account.h"
#include <iostream>

AccountNode::AccountNode() : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(authority::user) {}

AccountNode::AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type)
    : id(id), password(password), name(name), phone(phone), money(money), address(address), type(type) {}

std::ostream& operator<<(std::ostream& os, AccountNode& node) {
    os << "AccountId: " << node.id << "\n";
    os << "UserName: " << node.name << "\n";
    os << "UserPhone: " << node.phone << "\n";
    os << "Money: " << node.money << "\n";
    os << "Address: " << node.address << "\n";
    os << "UserType: ";
    if (node.type == authority::root) os << "root";
    else if (node.type == authority::admin) os << "admin";
    else os << "normal user";
    return os;
}
