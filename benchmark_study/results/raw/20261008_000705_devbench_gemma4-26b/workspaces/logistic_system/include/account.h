#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <iostream>
#include <string>

enum authority {
    root,
    admin,
    user
};

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
    AccountNode(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad, authority _t = user);

    friend std::ostream& operator<<(std::ostream& out, AccountNode& a);
    friend class LogisticSys;

    // Getter methods for LogisticSys to access private members
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }

    // Setter methods for LogisticSys to modify private members
    void setPassword(const std::string& _pwd) { password = _pwd; }
    void setMoney(double _m) { money = _m; }
};

#endif
