#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include <string>
#include <iostream>

class ExpressageNode {
private:
    std::string id;
    std::string sendUser;
    std::string receiveUser;
    std::string assignTime;
    std::string signTime;
    std::string remark;
    bool Flag;

public:
    ExpressageNode();
    ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, std::string assignTime, std::string signTime, std::string remark, bool Flag);
    
    bool Sign(std::string time);
    
    friend std::ostream& operator<<(std::ostream& os, const ExpressageNode& node);

    // Getter methods for LogisticSys to access private members
    std::string getId() const { return id; }
    std::string getSendUser() const { return sendUser; }
    std::string getReceiveUser() const { return receiveUser; }
    std::string getAssignTime() const { return assignTime; }
    std::string getSignTime() const { return signTime; }
    std::string getRemark() const { return remark; }
    bool getFlag() const { return Flag; }
    
    // Setter for signTime and Flag during Sign operation
    void setSignTime(std::string time) { signTime = time; }
    void setFlag(bool flag) { Flag = flag; }
};

#endif
