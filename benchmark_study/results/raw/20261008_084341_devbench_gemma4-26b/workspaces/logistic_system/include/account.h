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

    friend std::ostream& operator<<(std::ostream& out, const AccountNode& a);

    // Friend classes or methods to allow LogisticSys to access private members
    friend class LogisticSys;
    
    // Getters to allow main.cpp to access information
    std::string getId() const { return id; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }
};

#endif
