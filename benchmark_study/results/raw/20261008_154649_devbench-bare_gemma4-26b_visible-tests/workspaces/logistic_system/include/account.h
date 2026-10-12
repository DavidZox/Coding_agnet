#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

enum class authority {
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
    AccountNode(std::string _id, std::string _pwd, std::string _nm, std::string _ph, 
                double _m, std::string _ad, authority _t = authority::user);

    friend std::ostream& operator<<(std::ostream& out, AccountNode& a);
};

#endif
