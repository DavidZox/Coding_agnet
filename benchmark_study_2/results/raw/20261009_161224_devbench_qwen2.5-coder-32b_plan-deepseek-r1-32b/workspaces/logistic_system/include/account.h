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
    AccountNode(std::string id, std::string password, std::string name, std::string phone, double money, std::string address, authority type);

    friend std::ostream& operator<<(std::ostream& os, const AccountNode& account);

    bool changePassword(int accountIndex, const std::string& oldPassword, const std::string& newPassword);
    double queryMoney(int accountIndex) const;
    double addMoney(int accountIndex, double amount);

    // Getter methods
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }
};

#endif // ACCOUNT_H
