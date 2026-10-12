#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <vector>
#include <string>

enum class authority { root, admin, normal_user };

class AccountNode {
private:
    std::string id;
    std::string password;
    std::string name;
    std::string phone;
    double money;
    std::string address;
    authority type;

public:
    AccountNode();
    AccountNode(std::string, std::string, std::string, std::string, double, std::string, authority);
    friend std::ostream& operator<<(std::ostream&, const AccountNode&);
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }
    void setPassword(const std::string& newPwd) { password = newPwd; }
    double addMoney(double amount) { money += amount; return money; }
};

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
    std::string getId() const { return id; }
    std::string getSendUser() const { return sendUser; }
    std::string getReceiveUser() const { return receiveUser; }
    std::string getAssignTime() const { return assignTime; }
    std::string getSignTime() const { return signTime; }
    std::string getRemark() const { return remark; }
    bool isFlag() const { return Flag; }
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
    bool Regist(std::string, std::string, std::string, std::string, double, std::string);
    void init(std::string, std::string);
    void save(std::string, std::string);
    int Login(std::string, std::string);
    AccountNode queryInfo(int);
    bool changePassword(int, std::string, std::string);
    double queryMoney(int);
    double addMoney(int, double);
    bool assignExpressage(int, std::string, std::string, std::string);
    bool signExpressage(int, std::string, std::string);
    std::vector<ExpressageNode> queryAllExpressage(int);
    ExpressageNode queryExpressage(int, std::string);
};

#endif // LOGISTICS_H
