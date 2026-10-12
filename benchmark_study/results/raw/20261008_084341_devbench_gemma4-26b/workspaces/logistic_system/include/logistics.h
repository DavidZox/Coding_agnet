#ifndef LOGISTICS_H
#define LOGISTICS_H

#include <vector>
#include <string>
#include "account.h"
#include "expressage.h"

class LogisticSys {
private:
    std::vector<AccountNode> account;
    std::vector<ExpressageNode> expressage;
    int accountNum;
    int expressageNum;
    int rootIndex;

public:
    LogisticSys();
    ~LogisticSys();

    /**
     * @brief Registers a new account in the logistic system.
     * @param _id The ID of the account.
     * @param _pwd The password of the account.
     * @param _nm The name associated with the account.
     * @param _ph The phone number associated with the account.
     * @param _m The amount of money associated with the account.
     * @param _ad The address associated with the account.
     * @return true if registration is successful, false otherwise.
     */
    bool Regist(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad);

    /**
     * @brief Initializes the logistic system with account and expressage data from files.
     * @param accountFile The file path of the account data.
     * @param expressageFile The file path of the expressage data.
     */
    void init(std::string accountFile, std::string expressageFile);

    /**
     * @brief Saves the current state of the logistic system to files.
     * @param accountFile The file path to save the account data.
     * @param expressageFile The file path to save the expressage data.
     */
    void save(std::string accountFile, std::string expressageFile);

    /**
     * @brief Logs in to the logistic system with the given ID and password.
     * @param _id The ID of the account.
     * @param _pwd The password of the account.
     * @return The index of the account in the system if login is successful, -1 otherwise.
     */
    int Login(std::string _id, std::string _pwd);

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
     * @return true if the password is successfully changed, false otherwise.
     */
    bool changePassword(int curAccount, std::string oldpwd, std::string newpwd);

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
     * @param curAccount The index of the current account.
     * @param receiverId The ID of the receiver of the expressage.
     * @param remark The remark for the expressage.
     * @param time The time when the expressage is assigned.
     * @return true if the expressage is successfully assigned, false otherwise.
     */
    bool assignExpressage(int curAccount, std::string receiverId, std::string remark, std::string time);

    /**
     * @brief Signs an expressage of the current account.
     * @param curAccount The index of the current account.
     * @param id The ID of the expressage to sign.
     * @param time The time when the expressage is signed.
     * @return true if the expressage is successfully signed, false otherwise.
     */
    bool signExpressage(int curAccount, std::string id, std::string time);

    /**
     * @brief Queries all expressages of the current account.
     * @param curAccount The index of the current account.
     * @return A vector of ExpressageNode objects of all expressages of the current account.
     */
    std::vector<ExpressageNode> queryAllExpressage(int curAccount);

    /**
     * @brief Retrieves the information of the specified expressage assigned to the specified account.
     * @param curAccount The index of the current account.
     * @param id The ID of the expressage to query.
     * @return The ExpressageNode object representing the expressage information.
     */
    ExpressageNode queryExpressage(int curAccount, std::string id);
};

#endif
