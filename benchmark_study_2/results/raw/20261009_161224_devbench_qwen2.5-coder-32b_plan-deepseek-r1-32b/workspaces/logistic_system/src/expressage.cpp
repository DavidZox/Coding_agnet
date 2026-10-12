#include "expressage.h"
#include <iostream>
#include <iomanip>

ExpressageNode::ExpressageNode() : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime(""), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, std::string assignTime, std::string signTime, std::string remark, bool Flag)
    : id(id), sendUser(sendUser), receiveUser(receiveUser), assignTime(assignTime), signTime(signTime), remark(remark), Flag(Flag) {}

bool ExpressageNode::Sign(std::string user) {
    if (user == receiveUser && !Flag) {
        Flag = true;
        return true;
    }
    return false;
}

std::ostream& operator<<(std::ostream& os, const ExpressageNode& expressage) {
    os << "Expressage id: " << expressage.id << std::endl;
    os << "Sender: " << expressage.sendUser << std::endl;
    os << "Recipient: " << expressage.receiveUser << std::endl;
    os << "Send Time: " << expressage.assignTime << std::endl;
    os << "Status: " << (expressage.Flag ? "Delivered" : "Unsigned") << std::endl;
    os << "Sign Time: " << (expressage.Flag ? expressage.signTime : "NULL") << std::endl;
    os << "Remark: " << expressage.remark << std::endl;
    return os;
}
