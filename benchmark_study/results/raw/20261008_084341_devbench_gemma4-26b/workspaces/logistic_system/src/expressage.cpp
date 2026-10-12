#include "expressage.h"
#include <iostream>

ExpressageNode::ExpressageNode() 
    : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime(""), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string _id, std::string _sendUser, std::string _receiveUser, 
                               std::string _assignTime, std::string _signTime, std::string _remark, bool _Flag)
    : id(_id), sendUser(_sendUser), receiveUser(_receiveUser), assignTime(_assignTime), 
      signTime(_signTime), remark(_remark), Flag(_Flag) {}

bool ExpressageNode::Sign(std::string time) {
    signTime = time;
    Flag = true;
    return true;
}

std::ostream& operator<<(std::ostream& out, const ExpressageNode& a) {
    out << "Expressage id: " << a.getId() << "\n";
    out << "Sender: " << a.getSendUser() << "\n";
    out << "Recipient: " << a.getReceiveUser() << "\n";
    out << "Send Time: " << a.getAssignTime() << "\n";
    out << "Status: " << (a.getFlag() ? "Signed" : "Unsigned") << "\n";
    out << "Sign Time: " << (a.getFlag() ? a.getSignTime() : "NULL") << "\n";
    out << "Remark: " << a.getRemark();
    return out;
}

std::ostream& operator<<(std::ostream& out, ExpressageNode& a) {
    return out << (const ExpressageNode&)a;
}
