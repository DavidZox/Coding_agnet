#include "expressage.h"
#include <iostream>
#include <string>

// ExpressageNode 構造函數實現
ExpressageNode::ExpressageNode() : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime("NULL"), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, std::string assignTime, std::string signTime, std::string remark, bool flag)
    : id(id), sendUser(sendUser), receiveUser(receiveUser), assignTime(assignTime), signTime(signTime), remark(remark), Flag(flag) {}

// Sign 方法實現
bool ExpressageNode::Sign(std::string time) {
    // 根據規格，Sign 邏輯主要在 LogisticSys 中處理，這裡僅更新狀態
    this->signTime = time;
    this->Flag = true; // 標記為已簽收
    return true;
}

// ostream 運算子實現
std::ostream& operator<<(std::ostream& os, const ExpressageNode& node) {
    os << "Expressage id: " << node.id << "\n"
       << "Sender: " << node.sendUser << "\n"
       << "Recipient: " << node.receiveUser << "\n"
       << "Send Time: " << node.assignTime << "\n"
       << "Status: " << (node.Flag ? "Delivered" : "Unsigned") << "\n"
       << "Sign Time: " << node.signTime << "\n"
       << "Remark: " << node.remark;
    return os;
}
