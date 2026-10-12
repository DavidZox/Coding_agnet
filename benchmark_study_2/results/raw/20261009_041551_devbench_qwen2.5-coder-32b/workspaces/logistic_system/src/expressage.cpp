#include "expressage.h"

ExpressageNode::ExpressageNode() : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime(""), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string _id, std::string _sendUser, std::string _receiveUser, std::string _assignTime, std::string _signTime, std::string _remark, bool _Flag)
    : id(_id), sendUser(_sendUser), receiveUser(_receiveUser), assignTime(_assignTime), signTime(_signTime), remark(_remark), Flag(_Flag) {}

bool ExpressageNode::Sign(std::string _signTime) {
    if (!Flag) {
        signTime = _signTime;
        Flag = true;
        return true;
    }
    return false;
}

std::ostream& operator<<(std::ostream& out, const ExpressageNode& e) {
    out << "Expressage id: " << e.id << "\n"
        << "Sender: " << e.sendUser << "\n"
        << "Recipient: " << e.receiveUser << "\n"
        << "Send Time: " << e.assignTime << "\n"
        << "Status: " << (e.Flag ? "Delivered" : "Unsigned") << "\n"
        << "Sign Time: " << (e.Flag ? e.signTime : "NULL") << "\n"
        << "Remark: " << e.remark;
    return out;
}
