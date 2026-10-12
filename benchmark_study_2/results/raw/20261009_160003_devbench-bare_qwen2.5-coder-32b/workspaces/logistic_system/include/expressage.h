#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include <string>
#include <vector>
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
    ExpressageNode(const std::string& _id, const std::string& _sendUser, const std::string& _receiveUser, const std::string& _assignTime, const std::string& _signTime, const std::string& _remark, bool _Flag);
    bool Sign(const std::string& time);
    friend std::ostream& operator<<(std::ostream& out, const ExpressageNode& a);
};

#endif // EXPRESSAGE_H
