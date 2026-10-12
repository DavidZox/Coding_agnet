#include "expressage.h"

ExpressageNode::ExpressageNode() : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime(""), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, std::string assignTime, std::string signTime, std::string remark, bool Flag)
    : id(id), sendUser(sendUser), receiveUser(receiveUser), assignTime(assignTime), signTime(signTime), remark(remark), Flag(Flag) {}

bool ExpressageNode::Sign(std::string signTime) {
    if (!Flag) {
        this->signTime = signTime;
        Flag = true;
        return true;
    }
    return false;
}

std::ostream& operator<<(std::ostream& os, const ExpressageNode& expressage) {
    os << "Expressage id: " << expressage.id << "\n"
       << "Sender: " << expressage.sendUser << "\n"
       << "Recipient: " << expressage.receiveUser << "\n"
       << "Send Time: " << expressage.assignTime << "\n"
       << "Status: " << (expressage.Flag ? "Signed" : "Unsigned") << "\n"
       << "Sign Time: " << (expressage.Flag ? expressage.signTime : "NULL") << "\n"
       << "Remark: " << expressage.remark;
    return os;
}
