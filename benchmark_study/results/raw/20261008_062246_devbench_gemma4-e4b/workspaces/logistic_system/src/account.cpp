#include "account.h"
#include <iostream>
#include <string>
#include <sstream>
#include <cstring> // For strdup/strcpy if needed, though std::string handles most of it

// 實作 AccountNode 的析構子
AccountNode::~AccountNode() {
    // 由於在提供的程式碼中，成員變數 (id, password, name, phone, address) 都是 std::string，
    // std::string 會自動管理其內存，因此不需要手動釋放。
    // 如果它們是 char*，則需要釋放。基於當前實現，此處無需額外操作。
}

// 實作 AccountNode 的建構子
AccountNode::AccountNode() : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(root) {}

AccountNode::AccountNode(const std::string& id, const std::string& password, const std::string& name, const std::string& phone, double money, const std::string& address, authority type)
    : id(id), password(password), name(name), phone(phone), money(money), address(address), type(type) {}

// 實作複製建構子
AccountNode::AccountNode(const AccountNode& other)
    : id(other.id), password(other.password), name(other.name), phone(other.phone), money(other.money), address(other.address), type(other.type) {}

// 實作賦值運算子
AccountNode& AccountNode::operator=(const AccountNode& other) {
    if (this != &other) {
        id = other.id;
        password = other.password;
        name = other.name;
        phone = other.phone;
        money = other.money;
        address = other.address;
        type = other.type;
    }
    return *this;
}

// 實作 setter 方法
void AccountNode::setPassword(const std::string& newPassword) {
    password = newPassword;
}

void AccountNode::setMoney(double newMoney) {
    money = newMoney;
}

// 實作 addMoney 方法
void AccountNode::addMoney(double amount) {
    money += amount;
}

// 實作 ostream 運算子
std::ostream& operator<<(std::ostream& os, const AccountNode& node) {
    // 輸出格式要求: username password name phone number address user_type
    // 這裡的 type 應該是 int (0/1/2) 根據 PRD.md 的描述
    os << node.id << " " << node.password << " " << node.name << " " << node.phone << " " << node.money << " " << node.address << " " << node.type;
    return os;
}
