#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <vector>
#include <string>
#include <iostream>

// Forward declarations for AccountNode and ExpressageNode
// Assuming these structures/classes are defined or available elsewhere,
// but for completeness based on UML, we define minimal structures here
// or rely on them being fully defined in their respective headers.

// Since AccountNode and ExpressageNode are used in LogisticSys,
// we must define them or include their headers.
// Based on the dependency structure, we assume they will be defined in their own headers.
// For this file, we rely on forward declarations or minimal definitions if they are complex.

// Minimal definitions based on UML_class.md for compilation context
enum authority {
    ROOT = 0,
    ADMIN = 1,
    NORMAL = 2
};

class AccountNode {
public:
    std::string id;
    std::string password;
    std::string name;
    std::string phone;
    double money;
    std::string address;
    authority type;

    AccountNode() : money(0.0), type(NORMAL) {}
    AccountNode(std::string i, std::string p, std::string n, std::string ph, double m, std::string a, authority t)
        : id(i), password(p), name(n), phone(ph), money(m), address(a), type(t) {}

    friend std::ostream& operator<<(std::ostream& os, const AccountNode& node);
};

class ExpressageNode {
public:
    std::string id;
    std::string sendUser;
    std::string receiveUser;
    std::string assignTime;
    std::string signTime;
    std::string remark;
    bool Flag;

    ExpressageNode() : Flag(false) {}
    ExpressageNode(std::string i, std::string su, std::string ru, std::string at, std::string st, std::string r, bool f)
        : id(i), sendUser(su), receiveUser(ru), assignTime(at), signTime(st), remark(r), Flag(f) {}

    bool Sign(std::string time);

    friend std::ostream& operator<<(std::ostream& os, const ExpressageNode& node);
};


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
    bool Regist(std::string username, std::string password, std::string name, std::string phone, double balance, std::string address);
    void init(std::string accountFile, std::string expressageFile);
    void save(std::string accountFile, std::string expressageFile);

    // Account Operations
    int Login(std::string username, std::string password);
    AccountNode queryInfo(int accountIndex);
    bool changePassword(int accountIndex, std::string oldPassword, std::string newPassword);
    double queryMoney(int accountIndex);
    double addMoney(int accountIndex, double amount);

    // Logistics Operations
    bool assignExpressage(int senderIndex, std::string recipientUsername, std::string remark, std::string sendTime);
    bool signExpressage(int accountIndex, std::string logisticsId, std::string signTime);

    // Query Operations
    std::vector<ExpressageNode> queryAllExpressage(int accountIndex);
    ExpressageNode queryExpressage(int accountIndex, std::string logisticsId);
};

#endif // LOGISTICS_H
