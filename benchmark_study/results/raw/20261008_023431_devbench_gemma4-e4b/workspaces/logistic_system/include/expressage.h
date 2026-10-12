#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include <string>
#include <iostream>
#include <ostream>

class ExpressageNode {
private:
    std::string id;
    std::string sendUser;
    std::string receiveUser;
    std::string assignTime;
    std::string signTime;
    std::string remark;
    bool Flag; // 0: not delivered, 1: delivered

public:
    // Default constructor
    ExpressageNode();

    // Parameterized constructor
    ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, std::string assignTime, std::string signTime, std::string remark, bool flag);

    // Method to sign for the package
    bool Sign(std::string time);

    // Friend declaration for stream insertion operator
    friend std::ostream& operator<<(std::ostream& os, const ExpressageNode& node);
};

#endif // EXPRESSAGE_H
