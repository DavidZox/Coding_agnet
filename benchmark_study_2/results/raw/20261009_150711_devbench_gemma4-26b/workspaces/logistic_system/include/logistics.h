#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <vector>
#include <string>
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
    AccountNode queryInfo(int);
    bool changePassword(int idx, std::string opwd, std::string pwd);
    double queryMoney(int idx);
    double addMoney(int idx, double amount);
    bool assignExpressage(int senderIdx, std::string receiveUser, std::string remark, std::string time);
    bool signExpressage(int receiverIdx, std::string expressageId, std::string time);
    std::vector<ExpressageNode> queryAllExpressage(int idx);
    ExpressageNode queryExpressage(int idx, std::string expressageId);
    std::vector<ExpressageNode> queryAlls(int userIdx);
    std::vector<ExpressageNode> queryAllr(int userIdx);
    std::vector<ExpressageNode> queryBySender(int userIdx, std::string x);
    std::vector<ExpressageNode> queryByReceiver(int userIdx, std::string x);
    std::vector<ExpressageNode> queryByTime(int userIdx, std::string t);
};

#endif
