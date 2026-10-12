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
    void init(const std::string& accountFilePath, const std::string& expressageFilePath);
    void save(const std::string& accountFilePath, const std::string& expressageFilePath);
    int Login(const std::string& id, const std::string& pwd);
    bool Regist(const std::string& id, const std::string& pwd, const std::string& name, const std::string& phone, double money, const std::string& address);
    bool changePassword(int accountIndex, const std::string& oldPwd, const std::string& newPwd);
    AccountNode queryInfo(int accountIndex);
    double queryMoney(int accountIndex);
    double addMoney(int accountIndex, double amount);
    bool assignExpressage(int accountIndex, const std::string& receiverId, const std::string& remark, const std::string& time);
    bool signExpressage(int accountIndex, const std::string& expressageId, const std::string& time);
    std::vector<ExpressageNode> queryAllExpressage(int accountIndex);
    ExpressageNode queryExpressage(int accountIndex, const std::string& expressageId);
};

#endif // LOGISTICS_H
