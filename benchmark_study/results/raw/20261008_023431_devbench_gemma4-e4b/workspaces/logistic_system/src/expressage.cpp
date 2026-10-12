#include "expressage.h"
#include <iostream>
#include <string>
#include <sstream>

// ExpressageNode 構造函數實作
ExpressageNode::ExpressageNode() : id(""), sendUser(""), receiveUser(""), assignTime(""), signTime("NULL"), remark(""), Flag(false) {}

ExpressageNode::ExpressageNode(std::string id_val, std::string sendUser_val, std::string receiveUser_val, std::string assignTime_val, std::string signTime_val, std::string remark_val, bool flag_val)
    : id(id_val), sendUser(sendUser_val), receiveUser(receiveUser_val), assignTime(assignTime_val), signTime(signTime_val), remark(remark_val), Flag(flag_val) {}

// 重載 ostream& operator<< 函式
std::ostream& operator<<(std::ostream& os, const ExpressageNode& node) {
    os << "Expressage id: " << node.id << "\n";
    os << "Sender: " << node.sendUser << "\n";
    os << "Recipient: " << node.receiveUser << "\n";
    os << "Send Time: " << node.assignTime << "\n";
    os << "Status: " << (node.Flag ? "Delivered" : "Unsigned") << "\n";
    os << "Sign Time: " << node.signTime << "\n";
    os << "Remark: " << node.remark << "\n";
    return os;
}

// Sign 函式實作
// 根據規格文件，簽署操作的邏輯在 LogisticSys 中處理，這裡的 Sign 函式應反映單個節點的狀態變化。
// 由於缺乏完整的上下文（如是否是正確的接收者、是否已簽署），這裡實作一個基礎的邏輯：
// 如果尚未簽署 (Flag == false) 且傳入的時間有效，則標記為已簽署。
bool ExpressageNode::Sign(std::string signTime_val) {
    if (Flag == true) {
        // 已經簽署過
        return false;
    }
    // 假設傳入的 signTime_val 是有效的簽署時間
    this->signTime = signTime_val;
    this->Flag = true; // 標記為已簽署/已送達
    return true;
}
