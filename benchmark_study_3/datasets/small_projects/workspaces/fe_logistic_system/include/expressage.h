#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include "account.h"

#include <string>
#include <vector>
#include <time.h>
#include <stdio.h>
#include <cstring>

struct ExpressageNode {
    string id;
    string sendUser;
    string receiveUser;
    string assignTime;
    string signTime;
    string remark;
    bool Flag;
    ExpressageNode();
    ExpressageNode(
        string _id,
        string _sendUser,
        string _receiveUser,
        string _assignTime,
        string _signTime,
        string _remark,
        bool _Flag
    );
    friend ostream& operator << (ostream& o, ExpressageNode &a); 
};

#endif