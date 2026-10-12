#include "account.h"

AccountNode::AccountNode() 
    : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(authority::normal_user) {}

AccountNode::AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type)
    : id(id), password(password), name(name), phone(phone), money(money), address(address), type(type) {}

std::string AccountNode::getId() const {
    return id;
}

std::string AccountNode::getPassword() const {
    return password;
}

void AccountNode::setPassword(const std::string& new_password) {
    password = new_password;
}

std::string AccountNode::getName() const {
    return name;
}

std::string AccountNode::getPhone() const {
    return phone;
}

double AccountNode::getMoney() const {
    return money;
}

void AccountNode::setMoney(double new_money) {
    money = new_money;
}

std::string AccountNode::getAddress() const {
    return address;
}

authority AccountNode::getType() const {
    return type;
}

std::ostream& operator<<(std::ostream& os, const AccountNode& node) {
    os << node.id << " " << node.password << " " << node.name << " " << node.phone << " " 
       << node.money << " " << node.address << " " << static_cast<int>(node.type);
    return os;
}
