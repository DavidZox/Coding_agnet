#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <string>
#include <vector>
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
    bool Regist(const std::string& _id, const std::string& _pwd, const std::string& _nm, const std::string& _ph, double _m, const std::string& _ad);
    void init(const std::string& accountFile, const std::string& expressageFile);
    void save(const std::string& accountFile, const std::string& expressageFile);
    int Login(const std::string& _id, const std::string& _pwd);
    AccountNode queryInfo(int curAccount);
    bool changePassword(int curAccount, const std::string& oldpwd, const std::string& newpwd);
    double queryMoney(int curAccount);
    double addMoney(int curAccount, double money);
    bool assignExpressage(int curAccount, const std::string& receiverId, const std::string& remark, const std::string& time);
    bool signExpressage(int curAccount, const std::string& id, const std::string& time);
    std::vector<ExpressageNode> queryAllExpressage(int curAccount);
    ExpressageNode queryExpressage(int curAccount, const std::string& id);
};

#endif // LOGISTICS_H
