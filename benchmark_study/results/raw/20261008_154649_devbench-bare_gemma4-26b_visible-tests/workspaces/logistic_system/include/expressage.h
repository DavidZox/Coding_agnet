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

    ExpressageNode();
    ExpressageNode(std::string _id, std::string _sendUser, std::string _receiveUser, 
                   std::string _assignTime, std::string _signTime, std::string _remark, bool _Flag);

    bool Sign(std::string time);

    friend std::ostream& operator<<(std::ostream& out, ExpressageNode& a);
};

#endif
