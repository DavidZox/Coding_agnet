#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <string>
#include <vector>
#include <iostream>
#include "account.h"
#include "expressage.h"

class LogisticSys {
private:
    std::vector<AccountNode> account;
    std::vector<ExpressageNode> expressage;
    int accountNum;
    int expressageNum;
    int rootIndex;

public:
    LogisticSys();
    ~LogisticSys();

    bool Regist(std::string id, std::string pwd, std::string name, std::string phone, double money, std::string address);
    void init(std::string accountFile, std::string expressageFile);
    void save(std::string accountFile, std::string expressageFile);
    int Login(std::string id, std::string pwd);
    AccountNode queryInfo(int index);
    bool changePassword(int index, std::string opwd, std::string npwd);
    double queryMoney(int index);
    double addMoney(int index, double amount);
    bool assignExpressage(int senderIndex, std::string receiverId, std::string remark, std::string time);
    bool signExpressage(int receiverIndex, std::string expressageId, std::string time);
    std::vector<ExpressageNode> queryAllExpressage(int index);
    ExpressageNode queryExpressage(int index, std::string expressageId);
};

#endif
