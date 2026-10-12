#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

enum authority {
    root = 0,
    admin = 1,
    user = 2
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

    AccountNode();
    AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type);

    // Getters for testing and system use
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }

    // Setters for system use
    void setPassword(const std::string& new_pwd) { password = new_pwd; }
    void setMoney(double new_money) { money = new_money; }

    friend std::ostream& operator<<(std::ostream& os, const AccountNode& node);
};

#endif
