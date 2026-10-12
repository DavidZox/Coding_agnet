#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

enum class authority {
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
    AccountNode(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad, authority _t = authority::user);

    friend std::ostream& operator<<(std::ostream& out, AccountNode& a);

    // Getters and Setters for LogisticSys to use
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    void setPassword(const std::string& new_pwd) { password = new_pwd; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    void setMoney(double m) { money = m; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }
};

#endif
