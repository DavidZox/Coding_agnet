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
private:
    std::string id;
    std::string password;
    std::string name;
    std::string phone;
    double money;
    std::string address;
    authority type;

public:
    AccountNode() : money(0.0), type(user) {}
    AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type)
        : id(id), password(password), name(name), phone(phone), money(money), address(address), type(type) {}

    friend std::ostream& operator<<(std::ostream& os, const AccountNode& node);

    // Getter methods for LogisticSys to access private members
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }

    // Setter methods for LogisticSys to modify private members
    void setPassword(std::string new_pwd) { password = new_pwd; }
    void setMoney(double new_money) { money = new_money; }
};

#endif
