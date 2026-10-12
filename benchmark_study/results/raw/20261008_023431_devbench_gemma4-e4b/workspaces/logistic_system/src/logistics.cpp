#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <algorithm>
#include <cmath>

// Helper function to convert authority enum to string
std::string authorityToString(authority type) {
    switch (type) {
        case authority::root: return "root";
        case authority::admin: return "admin";
        case authority::normal: return "normal user";
        default: return "unknown";
    }
}

// Helper function to convert string to authority enum
authority stringToAuthority(const std::string& str) {
    if (str == "0") return authority::root;
    if (str == "1") return authority::admin;
    if (str == "2") return authority::normal;
    return authority::normal; // Default or error case
}

// Helper function to generate Logistics ID
std::string generateLogisticsId(int count) {
    std::stringstream ss;
    ss << "KD" << std::setw(8) << std::setfill('0') << count;
    return ss.str();
}

// Implementation of LogisticSys methods

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

// Reads data from files and populates internal structures
void LogisticSys::init(const std::string& accountFile, const std::string& expressageFile) {
    // 1. Initialize Accounts
    std::ifstream accFile(accountFile);
    if (!accFile.is_open()) {
        std::cerr << "Warning: Account file not found. Starting with empty accounts." << std::endl;
        accountNum = 0;
    } else {
        std::string line;
        if (std::getline(accFile, line)) {
            std::stringstream ss(line);
            ss >> accountNum;
        }
        
        account.clear();
        for (int i = 0; i < accountNum; ++i) {
            std::string line;
            if (std::getline(accFile, line)) {
                std::stringstream ls(line);
                std::string username, password, name, phone, address, typeStr;
                double money;
                
                // Format: username password name phone money address type
                ls >> username >> password >> name >> phone >> money >> address >> typeStr;
                
                authority type = stringToAuthority(typeStr);
                account.emplace_back(username, password, name, phone, money, address, type);
            }
        }
        accFile.close();

        // Find root index (Type 0)
        for (int i = 0; i < account.size(); ++i) {
            if (account[i].type == authority::root) {
                rootIndex = i;
                break;
            }
        }
    }

    // 2. Initialize Expressages
    std::ifstream expFile(expressageFile);
    if (!expFile.is_open()) {
        std::cerr << "Warning: Expressage file not found. Starting with empty logistics." << std::endl;
        expressageNum = 0;
    } else {
        std::string line;
        if (std::getline(expFile, line)) {
            std::stringstream ss(line);
            ss >> expressageNum;
        }

        expressage.clear();
        for (int i = 0; i < expressageNum; ++i) {
            std::string line;
            if (std::getline(expFile, line)) {
                std::stringstream ls(line);
                std::string id, sender, receiver, sendTime, deliveryTime, remark;
                int status;
                
                // Format: Logistics ID Sender Username Recipient Username Shipment Date Delivery Date Logistics Status Logistics Remark
                // Note: The PRD example shows: KD00000001 test_id_1 test_id_2 2020-01-01 NULL 0 TestRemark
                // We need to handle the potential NULL for delivery date carefully.
                
                std::string statusStr;
                if (ls >> id >> sender >> receiver >> sendTime >> deliveryTime >> statusStr >> remark) {
                    int status_val = std::stoi(statusStr);
                    // Flag is true if delivered (status == 1)
                    bool flag = (status_val == 1); 
                    expressage.emplace_back(id, sender, receiver, sendTime, deliveryTime, remark, flag);
                }
            }
        }
        expFile.close();
    }
}

// Saves current state to files
void LogisticSys::save(const std::string& accountFile, const std::string& expressageFile) {
    // 1. Save Accounts
    std::ofstream accFile(accountFile);
    if (!accFile.is_open()) {
        std::cerr << "Error: Could not open account file for saving." << std::endl;
        return;
    }
    accFile << accountNum << "\n";
    for (const auto& acc : account) {
        accFile << acc.id << " " << acc.password << " " << acc.name << " " 
                << acc.phone << " " << std::fixed << std::setprecision(2) << acc.money << " " 
                << acc.address << " " << acc.type << "\n";
    }
    accFile.close();

    // 2. Save Expressages
    std::ofstream expFile(expressageFile);
    if (!expFile.is_open()) {
        std::cerr << "Error: Could not open expressage file for saving." << std::endl;
        return;
    }
    expFile << expressageNum << "\n";
    for (const auto& exp : expressage) {
        // File format: ID Sender Recipient SendDate DeliveryDate Status Remark
        // DeliveryDate: If delivered (Flag=true), use signTime. Otherwise, use "NULL" as per PRD example for undelivered.
        std::string finalDeliveryDate = exp.Flag ? exp.signTime : "NULL"; 
        
        std::string status_str = exp.Flag ? "1" : "0";
        
        expFile << exp.id << " " << exp.sendUser << " " << exp.receiveUser << " " 
                << exp.assignTime << " " << finalDeliveryDate << " " 
                << status_str << " " << exp.remark << "\n";
    }
    expFile.close();
}

// Attempts to log in a user
int LogisticSys::Login(const std::string& username, const std::string& password) {
    for (int i = 0; i < account.size(); ++i) {
        if (account[i].id == username && account[i].password == password) {
            // Success: return index of the logged-in user
            return i;
        }
    }
    // Failure
    return -1;
}

// Registers a new user
bool LogisticSys::Regist(const std::string& username, const std::string& password, const std::string& name, 
                        const std::string& phone, double initialMoney, const std::string& address) {
    // Check if username exists
    for (const auto& acc : account) {
        if (acc.id == username) {
            return false; // Failed: Username exists
        }
    }

    // Register new user (Default type is normal user = 2)
    // PRD specifies initial balance is provided, and type is normal (2) if not specified otherwise.
    account.emplace_back(username, password, name, phone, initialMoney, address, authority::NORMAL);
    
    return true; // Succeed
}

// Retrieves account information for a given index
AccountNode LogisticSys::queryInfo(int index) const {
    if (index >= 0 && index < account.size()) {
        return account[index];
    }
    // Return a dummy/invalid node if index is out of bounds
    return AccountNode("", "", "", "", 0.0, "", authority::NORMAL);
}

// Changes the password for a user
bool LogisticSys::changePassword(int index, const std::string& oldPassword, const std::string& newPassword) {
    if (index < 0 || index >= account.size()) {
        return false; // Invalid index
    }
    if (account[index].password == oldPassword) {
        account[index].password = newPassword;
        return true; // Succeed
    }
    return false; // Failed: Old password incorrect
}

// Gets the current user's balance
double LogisticSys::queryMoney(int index) const {
    if (index >= 0 && index < account.size()) {
        return account[index].money;
    }
    return -1.0; // Error indicator
}

// Adds money to the user's balance
double LogisticSys::addMoney(int index, double amount) {
    if (index < 0 || index >= account.size()) {
        return -1.0; // Error indicator
    }
    if (amount < 0) {
        return -2.0; // Failed: Negative amount
    }
    account[index].money += amount;
    return account[index].money;
}

// Sends a package
bool LogisticSys::assignExpressage(int senderIndex, const std::string& recipientUsername, 
                                  const std::string& remark, const std::string& sendTime) {
=======
// Signs for a package
bool LogisticSys::signExpressage(int currentIndex, const std::string& logisticsId, const std::string& signTime) {
    
    // 1. Find the expressage
    int expIndex = -1;
    for (int i = 0; i < expressage.size(); ++i) {
        if (expressage[i].id == logisticsId) {
            expIndex = i;
            break;
        }
    }

    if (expIndex == -1) {
        return false; // Logistics information does not exist
    }

    // 2. Check if current user is the recipient
    if (account[currentIndex].id != expressage[expIndex].receiveUser) {
        return false; // Current user is not the recipient
    }

    // 3. Update status
    expressage[expIndex].signTime = signTime;
    expressage[expIndex].Flag = true; // Delivered
    
    return true; // Succeed
}

// Queries all packages related to the current user
std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int currentIndex) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    // Check authorization: Root/Admin can query all, Normal user can only query if sender or recipient
    bool isAdmin = (account[currentIndex].type == authority::admin || account[currentIndex].type == authority::root);
    
    for (const auto& exp : expressage) {
        bool isSender = (exp.sendUser == currentUser);
        bool isRecipient = (exp.receiveUser == currentUser);
        
        if (isAdmin || isSender || isRecipient) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries all packages sent by the current user
std::vector<ExpressageNode> LogisticSys::queryAllSentExpressage(int currentIndex) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    for (const auto& exp : expressage) {
        if (exp.sendUser == currentUser) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries all packages received by the current user
std::vector<ExpressageNode> LogisticSys::queryAllReceivedExpressage(int currentIndex) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    for (const auto& exp : expressage) {
        if (exp.receiveUser == currentUser) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries packages sent by a specific user X
std::vector<ExpressageNode> LogisticSys::querySentByUsername(int currentIndex, const std::string& usernameX) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    // Authorization check: Root/Admin can query all, Normal user can only query if they are sender or recipient of the queried package
    bool isAdmin = (account[currentIndex].type == authority::admin || account[currentIndex].type == authority::root);

    for (const auto& exp : expressage) {
        if (exp.sendUser == usernameX) {
            // Normal user restriction: Must be sender or recipient of the package being queried
            if (!isAdmin && exp.receiveUser != currentUser && exp.sendUser != currentUser) {
                continue; // Skip if not authorized
            }
            results.push_back(exp);
        }
    }
    return results;
}

// Queries packages received from a specific user X
std::vector<ExpressageNode> LogisticSys::queryReceivedFromUsername(int currentIndex, const std::string& usernameX) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    // Authorization check: Root/Admin can query all, Normal user can only query if they are sender or recipient of the queried package
    bool isAdmin = (account[currentIndex].type == authority::admin || account[currentIndex].type == authority::root);

    for (const auto& exp : expressage) {
        if (exp.receiveUser == currentUser && exp.sendUser == usernameX) {
            // Normal user restriction: Must be sender or recipient of the package being queried
            if (!isAdmin && exp.receiveUser != currentUser && exp.sendUser != currentUser) {
                continue; // Should not happen based on filter, but kept for strict adherence if logic changes
            }
            results.push_back(exp);
        }
    }
    return results;
}

// Queries packages sent on a specific date T
std::vector<ExpressageNode> LogisticSys::queryBySendTime(const std::string& timeT) const {
    std::vector<ExpressageNode> results;
    
    for (const auto& exp : expressage) {
        if (exp.assignTime == timeT) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries a specific package by ID
ExpressageNode LogisticSys::queryExpressage(const std::string& logisticsId) const {
    for (const auto& exp : expressage) {
        if (exp.id == logisticsId) {
            return exp;
        }
    }
    // Return a default/invalid node if not found
    return ExpressageNode("", "", "", "", "", "", false);
}
    
    // 1. Find the expressage
    int expIndex = -1;
    for (int i = 0; i < expressage.size(); ++i) {
        if (expressage[i].id == logisticsId) {
            expIndex = i;
            break;
        }
    }

    if (expIndex == -1) {
        return false; // Logistics information does not exist
    }

    // 2. Check if current user is the recipient
    if (account[currentIndex].id != expressage[expIndex].receiveUser) {
        return false; // Current user is not the recipient
    }

    // 3. Update status
    expressage[expIndex].signTime = signTime;
    expressage[expIndex].Flag = true; // Delivered
    
    return true; // Succeed
}

// Queries all packages related to the current user
std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int currentIndex) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    // Check authorization: Root/Admin can query all, Normal user can only query if sender or recipient
    bool isAdmin = (account[currentIndex].type == authority::admin || account[currentIndex].type == authority::root);
    
    for (const auto& exp : expressage) {
        bool isSender = (exp.sendUser == currentUser);
        bool isRecipient = (exp.receiveUser == currentUser);
        
        if (isAdmin || isSender || isRecipient) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries all packages sent by the current user
std::vector<ExpressageNode> LogisticSys::queryAllSentExpressage(int currentIndex) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    for (const auto& exp : expressage) {
        if (exp.sendUser == currentUser) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries all packages received by the current user
std::vector<ExpressageNode> LogisticSys::queryAllReceivedExpressage(int currentIndex) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    for (const auto& exp : expressage) {
        if (exp.receiveUser == currentUser) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries packages sent by a specific user X
std::vector<ExpressageNode> LogisticSys::querySentByUsername(int currentIndex, const std::string& usernameX) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    // Authorization check: Root/Admin can query all, Normal user can only query if they are sender or recipient of the queried package
    bool isAdmin = (account[currentIndex].type == authority::admin || account[currentIndex].type == authority::root);

    for (const auto& exp : expressage) {
        if (exp.sendUser == usernameX) {
            // Normal user restriction: Must be sender or recipient of the package being queried
            if (!isAdmin && exp.receiveUser != currentUser && exp.sendUser != currentUser) {
                continue; // Skip if not authorized
            }
            results.push_back(exp);
        }
    }
    return results;
}

// Queries packages received from a specific user X
std::vector<ExpressageNode> LogisticSys::queryReceivedFromUsername(int currentIndex, const std::string& usernameX) const {
    std::vector<ExpressageNode> results;
    const std::string& currentUser = account[currentIndex].id;
    
    // Authorization check: Root/Admin can query all, Normal user can only query if they are sender or recipient of the queried package
    bool isAdmin = (account[currentIndex].type == authority::admin || account[currentIndex].type == authority::root);

    for (const auto& exp : expressage) {
        if (exp.receiveUser == currentUser && exp.sendUser == usernameX) {
            // Normal user restriction: Must be sender or recipient of the package being queried
            if (!isAdmin && exp.receiveUser != currentUser && exp.sendUser != currentUser) {
                continue; // Should not happen based on filter, but kept for strict adherence if logic changes
            }
            results.push_back(exp);
        }
    }
    return results;
}

// Queries packages sent on a specific date T
std::vector<ExpressageNode> LogisticSys::queryBySendTime(const std::string& timeT) const {
    std::vector<ExpressageNode> results;
    
    for (const auto& exp : expressage) {
        if (exp.assignTime == timeT) {
            results.push_back(exp);
        }
    }
    return results;
}

// Queries a specific package by ID
ExpressageNode LogisticSys::queryExpressage(const std::string& logisticsId) const {
    for (const auto& exp : expressage) {
        if (exp.id == logisticsId) {
            return exp;
        }
    }
    // Return a default/invalid node if not found
    return ExpressageNode("", "", "", "", "", "", false);
}

// Retrieves account information for a given index
AccountNode LogisticSys::queryInfo(int index) const {
    if (index >= 0 && index < account.size()) {
        return account[index];
    }
    // Return a dummy/invalid node if index is out of bounds
    return AccountNode("", "", "", "", 0.0, "", authority::normal);
}

// Changes the password for a user
bool LogisticSys::changePassword(int index, const std::string& oldPassword, const std::string& newPassword) {
    if (index < 0 || index >= account.size()) {
        return false; // Invalid index
    }
    if (account[index].password == oldPassword) {
        account[index].password = newPassword;
        return true; // Succeed
    }
    return false; // Failed: Old password incorrect
}

// Attempts to log in a user
int LogisticSys::Login(const std::string& username, const std::string& password) {
    for (int i = 0; i < account.size(); ++i) {
        if (account[i].id == username && account[i].password == password) {
            // Success: return index of the logged-in user
            return i;
        }
    }
    // Failure
    return -1;
}

// Initializes system by reading data from files
void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    // 1. Initialize Accounts
    std::ifstream accFile(accountFile);
    if (!accFile.is_open()) {
        std::cerr << "Warning: Account file not found. Starting with empty accounts." << std::endl;
        accountNum = 0;
    } else {
        std::string line;
        if (std::getline(accFile, line)) {
            std::stringstream ss(line);
            ss >> accountNum;
        }
        
        account.clear();
        for (int i = 0; i < accountNum; ++i) {
            std::string line;
            if (std::getline(accFile, line)) {
                std::stringstream ls(line);
                std::string username, password, name, phone, address, typeStr;
                double money;
                
                // Format: username password name phone money address type
                ls >> username >> password >> name >> phone >> money >> address >> typeStr;
                
                authority type = stringToAuthority(typeStr);
                account.emplace_back(username, password, name, phone, money, address, type);
            }
        }
        accFile.close();

        // Find root index (Type 0)
        for (int i = 0; i < account.size(); ++i) {
            if (account[i].type == authority::ROOT) {
                rootIndex = i;
                break;
            }
        }
    }

    // 2. Initialize Expressages
    std::ifstream expFile(expressageFile);
    if (!expFile.is_open()) {
        std::cerr << "Warning: Expressage file not found. Starting with empty logistics." << std::endl;
        expressageNum = 0;
    } else {
        std::string line;
        if (std::getline(expFile, line)) {
            std::stringstream ss(line);
            ss >> expressageNum;
        }

        expressage.clear();
        for (int i = 0; i < expressageNum; ++i) {
            std::string line;
            if (std::getline(expFile, line)) {
                std::stringstream ls(line);
                std::string id, sender, receiver, sendTime, deliveryTime, remark;
                std::string statusStr;
                
                // Format: Logistics ID Sender Username Recipient Username Shipment Date Delivery Date Logistics Status Logistics Remark
                // PRD example: KD00000001 test_id_1 test_id_2 2020-01-01 NULL 0 TestRemark
                
                if (ls >> id >> sender >> receiver >> sendTime >> deliveryTime >> statusStr >> remark) {
                    int status_val = std::stoi(statusStr);
                    // Flag is true if delivered (status == 1)
                    bool flag = (status_val == 1); 
                    // Store the original deliveryTime from file, and use flag to determine final state
                    expressage.emplace_back(id, sender, receiver, sendTime, deliveryTime, remark, flag);
                }
            }
        }
        expFile.close();
    }
}

// Saves current state to files
void LogisticSys::save(const std::string& accountFile, const std::string& expressageFile) {
    // 1. Save Accounts
    std::ofstream accFile(accountFile);
    if (!accFile.is_open()) {
        std::cerr << "Error: Could not open account file for saving." << std::endl;
        return;
    }
    accFile << accountNum << "\n";
    for (const auto& acc : account) {
        accFile << acc.id << " " << acc.password << " " << acc.name << " " 
                << acc.phone << " " << std::fixed << std::setprecision(2) << acc.money << " " 
                << acc.address << " " << acc.type << "\n";
    }
    accFile.close();

    // 2. Save Expressages
    std::ofstream expFile(expressageFile);
    if (!expFile.is_open()) {
        std::cerr << "Error: Could not open expressage file for saving." << std::endl;
        return;
    }
    expFile << expressageNum << "\n";
    for (const auto& exp : expressage) {
        // File format: ID Sender Recipient SendDate DeliveryDate Status Remark
        // DeliveryDate: If delivered (Flag=true), use signTime. Otherwise, use "NULL" as per PRD example for undelivered.
        std::string finalDeliveryDate = exp.Flag ? exp.signTime : "NULL"; 
        
        std::string status_str = exp.Flag ? "1" : "0";
        
        expFile << exp.id << " " << exp.sendUser << " " << exp.receiveUser << " " 
                << exp.assignTime << " " << finalDeliveryDate << " " 
                << status_str << " " << exp.remark << "\n";
    }
    expFile.close();
}
