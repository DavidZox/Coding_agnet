#include "account.h"
#include <iostream>
#include <string>
#include <sstream>

// 實作 AccountNode 的預設建構子
AccountNode::AccountNode() : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(ROOT) {}

// 實作 AccountNode 的參數化建構子
AccountNode::AccountNode(std::string _id, std::string _password, std::string _name, std::string _phone, double _money, std::string _address, authority _type)
    : id(_id), password(_password), name(_name), phone(_phone), money(_money), address(_address), type(_type) {}

// 實作 ostream& operator<<(ostream&, AccountNode&)
std::ostream& operator<<(std::ostream& os, const AccountNode& node) {
    // 根據 PRD.md 的 account.txt 格式: username password name phone number address type
    os << node.id << " " << node.password << " " << node.name << " " << node.phone << " " << node.money << " " << node.address << " " << node.type;
    return os;
}
