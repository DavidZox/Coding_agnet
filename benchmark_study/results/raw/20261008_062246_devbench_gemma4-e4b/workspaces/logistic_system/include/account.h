#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <iostream>
#include <ostream>
#include <string>

// Authority type definition based on PRD.md and UML_class.md
enum authority {
    root = 0,
    admin = 1,
    normal_user = 2
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
    AccountNode(const std::string& id, const std::string& password, const std::string& name, const std::string& phone, double money, const std::string& address, authority type);

    // Rule of Five: Explicitly declare destructor, copy constructor, and assignment operator
    ~AccountNode();
    AccountNode(const AccountNode& other);
    AccountNode& operator=(const AccountNode& other);

    // Friend declaration for ostream overload
    friend std::ostream& operator<<(std::ostream& os, const AccountNode& node);

    // Getters (optional but good practice, though not explicitly required by UML for implementation)
    const std::string& getId() const { return id; }
    const std::string& getPassword() const { return password; }
    const std::string& getName() const { return name; }
    const std::string& getPhone() const { return phone; }
    double getMoney() const { return money; }
    const std::string& getAddress() const { return address; }
    authority getType() const { return type; }

    // Setters (needed for updates like password change)
    void setPassword(const std::string& newPassword);
    void setMoney(double newMoney);
    void addMoney(double amount); // Added method for balance modification
};

#endif // ACCOUNT_H
