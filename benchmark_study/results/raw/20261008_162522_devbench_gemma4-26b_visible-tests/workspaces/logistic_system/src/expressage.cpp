#include "expressage.h"

ExpressageNode::ExpressageNode() 
    : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime(""), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, 
                               std::string assignTime, std::string signTime, std::string remark, bool Flag)
    : id(id), sendUser(sendUser), receiveUser(receiveUser), assignTime(assignTime), 
      signTime(signTime), remark(remark), Flag(Flag) {}

bool ExpressageNode::Sign(std::string time) {
    if (Flag) {
        return false;
    }
    signTime = time;
    Flag = true;
    return true;
}

std::ostream& operator<<(std::ostream& os, const ExpressageNode& node) {
    os << "Expressage id: " << node.id << "\n";
    os << "Sender: " << node.sendUser << "\n";
    os << "Recipient: " << node.receiveUser << "\n";
    os << "Send Time: " << node.assignTime << "\n";
    os << "Status: " << (node.Flag ? "Signed" : "Unsigned") << "\n";
    os << "Sign Time: " << (node.signTime.empty() ? "NULL" : node.signTime) << "\n";
    os << "Remark: " << node.remark << "\n";
    return os;
}
