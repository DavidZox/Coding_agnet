#include "expressage.h"
#include <iostream>
#include <iomanip>

ExpressageNode::ExpressageNode() 
    : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime("NULL"), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, std::string assignTime, std::string signTime, std::string remark, bool Flag)
    : id(id), sendUser(sendUser), receiveUser(receiveUser), assignTime(assignTime), signTime(signTime), remark(remark), Flag(Flag) {}

bool ExpressageNode::Sign(std::string time) {
    signTime = time;
    Flag = true;
    return true;
}

std::ostream& operator<<(std::ostream& os, const ExpressageNode& node) {
    os << "Expressage id: " << node.getId() << "\n";
    os << "Sender: " << node.getSendUser() << "\n";
    os << "Recipient: " << node.getReceiveUser() << "\n";
    os << "Send Time: " << node.getAssignTime() << "\n";
    os << "Status: " << (node.getFlag() ? "Signed" : "Unsigned") << "\n";
    os << "Sign Time: " << node.getSignTime() << "\n";
    os << "Remark: " << node.getRemark() << "\n";
    return os;
}
