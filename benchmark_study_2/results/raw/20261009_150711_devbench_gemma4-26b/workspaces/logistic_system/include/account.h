#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

enum authority : int {
    root = 0,
    admin = 1,
    normal_user = 2
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

public:
    AccountNode();
    AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type);

    std::string getId() const;
    std::string getPassword() const;
    void setPassword(const std::string& new_password);
    std::string getName() const;
    std::string getPhone() const;
    double getMoney() const;
    void setMoney(double new_money);
    std::string getAddress() const;
    authority getType() const;

    friend std::ostream& operator<<(std::ostream& os, const AccountNode& node);
};

#endif
