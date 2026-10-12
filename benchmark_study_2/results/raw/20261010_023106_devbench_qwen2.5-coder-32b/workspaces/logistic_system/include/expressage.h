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
    ExpressageNode(std::string, std::string, std::string, std::string, std::string, std::string, bool);
    bool Sign(std::string);
    friend std::ostream& operator<<(std::ostream&, const ExpressageNode&);
};

#endif // EXPRESSAGE_H
