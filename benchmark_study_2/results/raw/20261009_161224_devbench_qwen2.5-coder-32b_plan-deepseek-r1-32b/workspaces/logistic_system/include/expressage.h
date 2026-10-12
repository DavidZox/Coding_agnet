#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include <string>

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
    bool Sign(std::string signTime);
    friend std::ostream& operator<<(std::ostream& os, const ExpressageNode& expressage);

    // Getter methods
    std::string getId() const { return id; }
    std::string getSendUser() const { return sendUser; }
    std::string getReceiveUser() const { return receiveUser; }
    std::string getAssignTime() const { return assignTime; }
    std::string getSignTime() const { return signTime; }
    std::string getRemark() const { return remark; }
    bool getFlag() const { return Flag; }
};

#endif // EXPRESSAGE_H
