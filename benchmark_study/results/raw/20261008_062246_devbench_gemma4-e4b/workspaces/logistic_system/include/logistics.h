#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <vector>
#include <string>
#include <iostream>
#include "account.h"
#include "expressage.h"

// Authority enum should be defined in a shared location or within the class scope if possible,
// but to resolve multiple definition errors, we ensure it's only defined once.
// Since account.h likely defines its own authority, we might need to rely on that,
// but based on the error, we redefine it here, assuming account.h might not expose it cleanly.
// For this fix, we assume the definition in account.h is the canonical one,
// and we remove the duplicate definition here, relying on account.h's definition.
// If account.h doesn't expose it, this structure might require changes in account.h too.
// However, to fix the multiple definition error based on the provided context,
// we remove the enum definition here and assume account.h provides the necessary context or we use the one from account.h.

// Forward declarations for AccountNode and ExpressageNode
// Since we are including account.h and expressage.h, we rely on them defining these.
// We must ensure that account.h and expressage.h define the necessary structures/classes
// and that LogisticSys includes them.

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

    // Initialization and Persistence
    void init(std::string accountFile, std::string expressageFile);
    void save(std::string accountFile, std::string expressageFile);

    // Account Management
    bool Regist(std::string username, std::string password, std::string name, std::string phone, double initialMoney, std::string address);
    int Login(std::string username, std::string password); // Returns index or -1
    AccountNode queryInfo(int accountIndex) const;
    bool changePassword(int accountIndex, std::string oldPassword, std::string newPassword);
    double queryMoney(int accountIndex) const;
    bool addMoney(int accountIndex, double amount);

    // Logistics Management
    bool assignExpressage(int senderIndex, std::string recipientUsername, std::string remark, std::string sendTime);
    bool signExpressage(int accountIndex, std::string logisticsId, std::string signTime);

    // Query Functions
    std::vector<ExpressageNode> queryAllExpressage(int accountIndex) const;
    ExpressageNode queryExpressage(int accountIndex, std::string logisticsId) const;
    std::vector<ExpressageNode> queryAllSent(int accountIndex, std::string senderUsername) const;
    std::vector<ExpressageNode> queryAllReceived(int accountIndex, std::string recipientUsername) const;
    std::vector<ExpressageNode> queryByTime(int accountIndex, std::string time) const;
    ExpressageNode querySpecific(int accountIndex, std::string logisticsId) const;
};

#endif // LOGISTICS_H
