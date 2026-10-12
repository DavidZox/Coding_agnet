#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

enum class authority { user, admin, root };

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
    AccountNode(const std::string& _id, const std::string& _pwd, const std::string& _nm, const std::string& _ph, double _m, const std::string& _ad, authority _t);
    friend std::ostream& operator<<(std::ostream& out, const AccountNode& a);
};

#endif // ACCOUNT_H
