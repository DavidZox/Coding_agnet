#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>

// authority type: 0/1/2 representing root/admin/normal user
enum authority {
    ROOT = 0,
    ADMIN = 1,
    NORMAL = 2
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
    // Default constructor
    AccountNode();

    // Parameterized constructor
    AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type);

    // Friend declaration for overloaded operator<<
    friend std::ostream& operator<<(std::ostream& os, const AccountNode& node);

    // Getters (necessary for LogisticSys to access private members)
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }

    // Setters (necessary for updates)
    void setPassword(const std::string& newPassword) { password = newPassword; }
    void setMoney(double newMoney) { money = newMoney; }
    void setType(authority newType) { type = newType; }
};

// Overloaded stream insertion operator
std::ostream& operator<<(std::ostream& os, const AccountNode& node);

#endif // ACCOUNT_H
