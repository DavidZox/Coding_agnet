#include "expressage.h"

ExpressageNode::ExpressageNode() : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime(""), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(const std::string& _id, const std::string& _sendUser, const std::string& _receiveUser, const std::string& _assignTime, const std::string& _signTime, const std::string& _remark, bool _Flag)
    : id(_id), sendUser(_sendUser), receiveUser(_receiveUser), assignTime(_assignTime), signTime(_signTime), remark(_remark), Flag(_Flag) {}

bool ExpressageNode::Sign(const std::string& time) {
    if (!Flag) {
        signTime = time;
        Flag = true;
        return true;
    }
    return false;
}

std::ostream& operator<<(std::ostream& out, const ExpressageNode& a) {
    out << "Expressage id: " << a.id << "\n"
        << "Sender: " << a.sendUser << "\n"
        << "Recipient: " << a.receiveUser << "\n"
        << "Send Time: " << a.assignTime << "\n"
        << "Status: " << (a.Flag ? "Signed" : "Unsigned") << "\n"
        << "Sign Time: " << (a.signTime.empty() ? "NULL" : a.signTime) << "\n"
        << "Remark: " << a.remark << "\n";
    return out;
}
