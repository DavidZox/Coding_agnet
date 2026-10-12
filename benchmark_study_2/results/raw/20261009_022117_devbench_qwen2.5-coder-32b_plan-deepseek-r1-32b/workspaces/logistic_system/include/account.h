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

    // Getter methods
    std::string getId() const { return id; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }
    std::string getPassword() const { return password; }

    // Setter methods
    void setPassword(std::string pwd) { password = pwd; }
    void setMoney(double amount) { money = amount; }
    void setAddress(std::string addr) { address = addr; }
};

#endif // ACCOUNT_H
