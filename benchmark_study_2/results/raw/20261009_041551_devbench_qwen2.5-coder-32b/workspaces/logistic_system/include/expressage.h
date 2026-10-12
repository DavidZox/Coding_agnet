#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include <string>
#include <iostream>

class ExpressageNode {
public:
    std::string id;
    std::string sendUser;
    std::string receiveUser;
    std::string assignTime;
    std::string signTime;
    std::string remark;
    bool Flag;

public:
    ExpressageNode();
    ExpressageNode(std::string _id, std::string _sendUser, std::string _receiveUser, std::string _assignTime, std::string _signTime, std::string _remark, bool _Flag);
    bool Sign(std::string _signTime);
    friend std::ostream& operator<<(std::ostream& out, const ExpressageNode& e);

    // Added public methods for LogisticSys to access private members
    std::string getId() const { return id; }
    std::string getSendUser() const { return sendUser; }
    std::string getReceiveUser() const { return receiveUser; }
    std::string getAssignTime() const { return assignTime; }
    std::string getSignTime() const { return signTime; }
    std::string getRemark() const { return remark; }
    bool getFlag() const { return Flag; }
    void setSignTime(const std::string& time) { signTime = time; }
    void setFlag(bool flag) { Flag = flag; }
};

#endif // EXPRESSAGE_H
