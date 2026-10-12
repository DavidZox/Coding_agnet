#include "expressage.h"

ExpressageNode::ExpressageNode() 
    : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime(""), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string _id, std::string _sendUser, std::string _receiveUser, 
                               std::string _assignTime, std::string _signTime, std::string _remark, bool _Flag)
    : id(_id), sendUser(_sendUser), receiveUser(_receiveUser), assignTime(_assignTime), 
      signTime(_signTime), remark(_remark), Flag(_Flag) {}

bool ExpressageNode::Sign(std::string time) {
    if (Flag) {
        return false;
    }
    signTime = time;
    Flag = true;
    return true;
}

std::ostream& operator<<(std::ostream& out, ExpressageNode& a) {
    out << "Expressage id: " << a.id << "\n";
    out << "Sender: " << a.sendUser << "\n";
    out << "Recipient: " << a.receiveUser << "\n";
    out << "Send Time: " << a.assignTime << "\n";
    out << "Status: " << (a.Flag ? "Signed" : "Unsigned") << "\n";
    out << "Sign Time: " << (a.signTime == "" ? "NULL" : a.signTime) << "\n";
    out << "Remark: " << a.remark << "\n";
    return out;
}
