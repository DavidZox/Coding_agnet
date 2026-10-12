#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <string>
#include <vector>
#include <iostream>
#include "account.h"
#include "expressage.h"

/**
 * @brief Manages the entire logistics system, including accounts and expressages.
 */
class LogisticSys {
private:
    std::vector<AccountNode> account;
    std::vector<ExpressageNode> expressage;
    int accountNum;
    int expressageNum;
    int rootIndex; // Index of the root user

public:
    /**
     * @brief Default constructor for LogisticSys.
     */
    LogisticSys();

    /**
     * @brief Destructor for LogisticSys.
     */
    ~LogisticSys();

    /**
     * @brief Registers a new account in the logistic system.
     * @param _id The ID of the account.
     * @param _pwd The password of the account.
     * @param _nm The name associated with the account.
     * @param _ph The phone number associated with the account.
     * @param _m The amount of money associated with the account.
     * @param _ad The address associated with the account.
     * @return True if registration is successful, false otherwise (e.g., ID exists).
     */
    bool Regist(const std::string& _id, const std::string& _pwd, const std::string& _nm, const std::string& _ph, double _m, const std::string& _ad);

    /**
     * @brief Initializes the logistic system with account and expressage data from files.
     * @param accountFile The file path of the account data.
     * @param expressageFile The file path of the expressage data.
     */
    void init(const std::string& accountFile, const std::string& expressageFile);

    /**
     * @brief Saves the current state of the logistic system to files.
     * @param accountFile The file path to save the account data.
     * @param expressageFile The file path to save the expressage data.
     */
    void save(const std::string& accountFile, const std::string& expressageFile);

    /**
     * @brief Logs in to the logistic system with the given ID and password.
     * @param _id The ID of the account.
     * @param _pwd The password of the account.
     * @return The index of the account in the system if login is successful, -1 otherwise.
     */
    int Login(const std::string& _id, const std::string& _pwd);

    /**
     * @brief Queries the information of the current account.
     * @param curAccount The index of the current account in the system.
     * @return The AccountNode object of the current account.
     */
    AccountNode queryInfo(int curAccount);

    /**
     * @brief Changes the password of the current account.
     * @param curAccount The index of the current account in the system.
     * @param oldpwd The old password of the account.
     * @param newpwd The new password of the account.
     * @return True if the password is successfully changed, false otherwise.
     */
    bool changePassword(int curAccount, const std::string& oldpwd, const std::string& newpwd);

    /**
     * @brief Queries the amount of money of the current account.
     * @param curAccount The index of the current account in the system.
     * @return The amount of money of the current account.
     */
    double queryMoney(int curAccount);

    /**
     * @brief Adds money to the current account.
     * @param curAccount The index of the current account in the system.
     * @param money The amount of money to add.
     * @return The new amount of money of the current account.
     */
    double addMoney(int curAccount, double money);

    /**
     * @brief Assigns an expressage to the current account.
     * @param curAccount The index of the current account in the system.
     * @param receiverId The ID of the receiver of the expressage.
     * @param remark The remark for the expressage.
     * @param time The time when the expressage is assigned.
     * @return True if the expressage is successfully assigned, false otherwise.
     */
    bool assignExpressage(int curAccount, const std::string& receiverId, const std::string& remark, const std::string& time);

    /**
     * @brief Signs an expressage of the current account.
     * @param curAccount The index of the current account in the system.
     * @param id The ID of the expressage.
     * @param time The time when the expressage is signed.
     * @return True if the expressage is successfully signed, false otherwise.
     */
    bool signExpressage(int curAccount, const std::string& id, const std::string& time);

    /**
     * @brief Queries all expressages related to the current account (sender or recipient).
     * @param curAccount The index of the current account in the system.
     * @return A vector of ExpressageNode objects of all expressages related to the current account.
     */
    std::vector<ExpressageNode> queryAllExpressage(int curAccount);

    /**
     * @brief Retrieves the information of the specified expressage assigned to the specified account.
     * @param curAccount The index of the current account.
     * @param id The ID of the expressage to query.
     * @return The ExpressageNode object representing the expressage information.
     */
    ExpressageNode queryExpressage(int curAccount, const std::string& id);
};

#endif // LOGISTICS_H
