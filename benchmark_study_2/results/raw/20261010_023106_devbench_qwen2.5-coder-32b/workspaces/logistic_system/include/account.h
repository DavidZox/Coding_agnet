#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

enum class authority { root, admin, normal_user };

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
    AccountNode(std::string, std::string, std::string, std::string, double, std::string, authority);

    friend std::ostream& operator<<(std::ostream&, const AccountNode&);

    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }
    void setPassword(const std::string& newPwd) { password = newPwd; }
    void setMoney(double amount) { money = amount; }
    double addMoney(int index, double amount) { money += amount; return money; }
};

#endif // ACCOUNT_H
