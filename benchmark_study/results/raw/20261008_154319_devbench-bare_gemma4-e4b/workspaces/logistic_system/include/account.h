#ifndef ACCOUNT_H
#define ACCOUNT_H

#include <string>
#include <iostream>
#include <vector>

// Forward declaration for ExpressageNode if needed, but for AccountNode itself, we only need basic types.
// We define the authority enum here as it's used in AccountNode.

enum authority {
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
    /**
     * @brief Default constructor for AccountNode.
     */
    AccountNode();

    /**
     * @brief Constructor for AccountNode.
     * @param _id The ID of the account.
     * @param _pwd The password of the account.
     * @param _nm The name associated with the account.
     * @param _ph The phone number associated with the account.
     * @param _m The amount of money associated with the account.
     * @param _ad The address associated with the account.
     * @param _t The authority type of the account.
     */
    AccountNode(_id, _pwd, _nm, _ph, _m, _ad, _t);

    /**
     * @brief Overloaded stream insertion operator for AccountNode.
     * @param out The output stream.
     * @param a The AccountNode object to be inserted into the stream.
     * @return The output stream after inserting the AccountNode object.
     */
    friend std::ostream& operator<<(std::ostream& out, const AccountNode& a);

    // Getters (needed for LogisticSys operations)
    std::string getId() const { return id; }
    std::string getPassword() const { return password; }
    std::string getName() const { return name; }
    std::string getPhone() const { return phone; }
    double getMoney() const { return money; }
    std::string getAddress() const { return address; }
    authority getType() const { return type; }

    // Setters (needed for updates)
    void setPassword(const std::string& newPwd) { password = newPwd; }
    void setMoney(double newMoney) { money = newMoney; }
    void setName(const std::string& newName) { name = newName; }
    void setAddress(const std::string& newAddress) { address = newAddress; }
};

#endif // ACCOUNT_H
