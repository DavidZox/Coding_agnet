#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

enum class authority {
    user = 2,
    admin = 1,
    root = 0
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
    AccountNode(std::string _id, std::string _pwd, std::string _nm, std::string _ph, 
                double _m, std::string _ad, authority _t = authority::user);

    friend std::ostream& operator<<(std::ostream& out, AccountNode& a);

    // Getters and Setters for system logic
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    void setPassword(const std::string& _pwd) { password = _pwd; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    void setMoney(double _m) { money = _m; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }
};

#endif
