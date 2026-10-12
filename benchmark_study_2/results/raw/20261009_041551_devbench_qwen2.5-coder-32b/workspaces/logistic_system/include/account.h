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

    // Added public methods for LogisticSys to access private members
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    void setPassword(const std::string& pwd) { password = pwd; }
    double getMoney() const { return money; }
    void setMoney(double m) { money = m; }
    authority getType() const { return type; }

    // Public access to private members
    std::string namePublic() const { return name; }
    std::string phonePublic() const { return phone; }
    std::string addressPublic() const { return address; }
};

#endif // ACCOUNT_H
