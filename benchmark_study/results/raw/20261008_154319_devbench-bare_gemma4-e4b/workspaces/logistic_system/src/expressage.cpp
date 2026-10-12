#include "expressage.h"
#include <iostream>
#include <sstream>
#include <iomanip>

// --- ExpressageNode Implementation ---

ExpressageNode::ExpressageNode() : Flag(false) {}

ExpressageNode::ExpressageNode(std::string _id, std::string _sendUser, std::string _receiveUser, std::string _assignTime, std::string _signTime, std::string _remark, bool _Flag)
    : id(_id), sendUser(_sendUser), receiveUser(_receiveUser), assignTime(_assignTime), signTime(_signTime), remark(_remark), Flag(_Flag) {}

bool ExpressageNode::Sign(std::string time) {
    if (Flag == false) {
        signTime = time;
        Flag = true;
        return true;
    }
    return false; // Already signed
}

std::ostream& operator<<(std::ostream& out, const ExpressageNode& a) {
    // Format required for query output:
    // Expressage id: KD00000001
    // Sender: test_id_1
    // Recipient: test_id_2
    // Send Time: 2020-01-01
    // Status: Unsigned/Delivered
    // Sign Time: NULL/YYYY-MM-DD
    // Remark: TestRemark
    
    std::string status_str = a.Flag ? "Delivered" : "Unsigned";
    std::string sign_time_out = a.signTime.empty() ? "NULL" : a.signTime;

    out << "Expressage id: " << a.id << "\n"
        << "Sender: " << a.sendUser << "\n"
        << "Recipient: " << a.receiveUser << "\n"
        << "Send Time: " << a.assignTime << "\n"
        << "Status: " << status_str << "\n"
        << "Sign Time: " << sign_time_out << "\n"
        << "Remark: " << a.remark;
    return out;
}
