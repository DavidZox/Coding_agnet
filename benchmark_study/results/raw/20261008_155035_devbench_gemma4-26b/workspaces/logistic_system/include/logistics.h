#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <vector>
#include <string>
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

    bool Regist(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad);
    void init(std::string accountFile, std::string expressageFile);
    void save(std::string accountFile, std::string expressageFile);
    int Login(std::string _id, std::string _pwd);
    AccountNode queryInfo(int curAccount);
    bool changePassword(int curAccount, std::string oldpwd, std::string newpwd);
    double queryMoney(int curAccount);
    double addMoney(int curAccount, double money);
    bool assignExpressage(int curAccount, std::string receiverId, std::string remark, std::string time);
    bool signExpressage(int curAccount, std::string id, std::string time);
    std::vector<ExpressageNode> queryAllExpressage(int curAccount);
    std::vector<ExpressageNode> queryAlls(int userIdx);
    std::vector<ExpressageNode> queryAllr(int userIdx);
    std::vector<ExpressageNode> qs(int userIdx, std::string x);
    std::vector<ExpressageNode> qr(int userIdx, std::string x);
    std::vector<ExpressageNode> qt(int userIdx, std::string t);
    ExpressageNode queryExpressage(int curAccount, std::string id);
};

#endif
