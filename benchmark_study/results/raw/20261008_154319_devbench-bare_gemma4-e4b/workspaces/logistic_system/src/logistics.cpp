#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <iostream>

// --- AccountNode Implementation ---

AccountNode::AccountNode() : money(0.0), type(user) {}

AccountNode::AccountNode(_id, _pwd, _nm, _ph, _m, _ad, _t)
    : id(_id), password(_pwd), name(_nm), phone(_ph), money(_m), address(_ad), type(_t) {}

std::ostream& operator<<(std::ostream& out, const AccountNode& a) {
    out << a.id << " " << a.password << " " << a.name << " " << a.phone << " "
        << std::fixed << std::setprecision(2) << a.money << " " << a.address << " " << a.type;
    return out;
}

// --- ExpressageNode Implementation ---

ExpressageNode::ExpressageNode() : Flag(false) {}

ExpressageNode::ExpressageNode(_id, _sendUser, _receiveUser, _assignTime, _signTime, _remark, _Flag)
    : id(_id), sendUser(_sendUser), receiveUser(_receiveUser), assignTime(_assignTime), signTime(_signTime), remark(_remark), Flag(_Flag) {}

bool ExpressageNode::Sign(std::string time) {
    if (Flag == false) {
        signTime = time;
        Flag = true;
        return true;
    }
    return false; // Already signed
}

std::ostream& operator<<(std::ostream& out, const ExpressageNode& a) {
    out << a.id << " " << a.sendUser << " " << a.receiveUser << " " << a.assignTime << " "
        << a.signTime << " " << a.Flag << " " << a.remark;
    return out;
}

// --- LogisticSys Implementation ---

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

bool LogisticSys::Regist(const std::string& _id, const std::string& _pwd, const std::string& _nm, const std::string& _ph, double _m, const std::string& _ad) {
    // Check if ID already exists
    for (const auto& acc : account) {
        if (acc.getId() == _id) {
            return false; // ID exists
        }
    }

    // Register new account (default type is user=2)
    account.emplace_back(_id, _pwd, _nm, _ph, _m, _ad, user);
    accountNum++;

    // If this is the first user, set them as root (assuming the first registered user is root for simplicity based on PRD example)
    if (accountNum == 1) {
        rootIndex = 0;
        // Manually set the first user to root type (0) if they are the first one registered
        account[0].type = root;
    }
    return true;
}

void LogisticSys::init(const std::string& accountFile, const std::string& expressageFile) {
    // 1. Initialize Accounts
    std::ifstream accFile(accountFile);
    if (!accFile.is_open()) {
        std::cerr << "Warning: Account file not found: " << accountFile << std::endl;
        return;
    }

    std::string line;
    if (std::getline(accFile, line)) {
        std::stringstream ss(line);
        ss >> accountNum;
    }

    account.clear();
    for (int i = 0; i < accountNum; ++i) {
        if (std::getline(accFile, line)) {
            std::stringstream ss(line);
            std::string id, pwd, name, phone, address;
            double money;
            authority type_val;

            // Read fields: username, password, name, phone, balance, address, user type
            ss >> id >> pwd >> name >> phone >> money >> address >> type_val;
            account.emplace_back(id, pwd, name, phone, money, address, type_val);
        }
    }
    accFile.close();

    // Determine root index after loading accounts
    rootIndex = -1;
    for (int i = 0; i < account.size(); ++i) {
        if (account[i].getType() == root) {
            rootIndex = i;
            break;
        }
    }


    // 2. Initialize Expressages
    std::ifstream expFile(expressageFile);
    if (!expFile.is_open()) {
        std::cerr << "Warning: Expressage file not found: " << expressageFile << std::endl;
        return;
    }

    expressage.clear();
    if (std::getline(expFile, line)) {
        std::stringstream ss(line);
        ss >> expressageNum;
    }

    for (int i = 0; i < expressageNum; ++i) {
        if (std::getline(expFile, line)) {
            std::stringstream ss(line);
            std::string id, sendUser, receiveUser, assignTime, signTimeStr, remark;
            int status_int;
            
            // Read fields: Logistics ID, Sender Username, Recipient Username, Shipment Date, Delivery Date, Logistics Status, Logistics Remark
            ss >> id >> sendUser >> receiveUser >> assignTime >> signTimeStr >> status_int >> remark;
            
            bool flag = (status_int == 1); // 1=delivered, 0=not delivered
            
            // Note: The PRD example shows status 0/1, but the UML suggests Flag is used. We map status 1 -> Flag=true (delivered).
            // The ExpressageNode constructor expects a bool Flag.
            expressage.emplace_back(id, sendUser, receiveUser, assignTime, signTimeStr, remark, flag);
        }
    }
    expFile.close();
}

void LogisticSys::save(const std::string& accountFile, const std::string& expressageFile) {
    // 1. Save Accounts
    std::ofstream accFile(accountFile);
    if (!accFile.is_open()) {
        std::cerr << "Error: Could not open account file for writing: " << accountFile << std::endl;
        return;
    }

    accFile << accountNum << "\n";
    for (const auto& acc : account) {
        accFile << acc << "\n";
    }
    accFile.close();

    // 2. Save Expressages
    std::ofstream expFile(expressageFile);
    if (!expFile.is_open()) {
        std::cerr << "Error: Could not open expressage file for writing: " << expressageFile << std::endl;
        return;
    }

    expFile << expressageNum << "\n";
    for (const auto& exp : expressage) {
        expFile << exp << "\n";
    }
    expFile.close();
}

int LogisticSys::Login(const std::string& _id, const std::string& _pwd) {
    for (int i = 0; i < account.size(); ++i) {
        if (account[i].getId() == _id && account[i].getPassword() == _pwd) {
            return i; // Return index
        }
    }
    return -1; // Login failed
}

AccountNode LogisticSys::queryInfo(int curAccount) {
    if (curAccount >= 0 && curAccount < account.size()) {
        return account[curAccount];
    }
    // Should not happen if called correctly after successful login
    return AccountNode(); 
}

bool LogisticSys::changePassword(int curAccount, const std::string& oldpwd, const std::string& newpwd) {
    if (curAccount >= 0 && curAccount < account.size()) {
        if (account[curAccount].getPassword() == oldpwd) {
            account[curAccount].setPassword(newpwd);
            return true;
        }
    }
    return false;
}

double LogisticSys::queryMoney(int curAccount) {
    if (curAccount >= 0 && curAccount < account.size()) {
        return account[curAccount].getMoney();
    }
    return -1.0; // Error indicator
}

double LogisticSys::addMoney(int curAccount, double money) {
    if (curAccount >= 0 && curAccount < account.size()) {
        account[curAccount].setMoney(account[curAccount].getMoney() + money);
        return account[curAccount].getMoney();
    }
    return -1.0; // Error indicator
}

bool LogisticSys::assignExpressage(int curAccount, const std::string& receiverId, const std::string& remark, const std::string& time) {
    // 1. Check sender balance
    double cost = 15.0;
    if (account[curAccount].getMoney() < cost) {
        return false; // Insufficient balance
    }

    // 2. Check recipient existence (if not root)
    bool recipientExists = (receiverId == "root_id");
    if (!recipientExists) {
        for (const auto& acc : account) {
            if (acc.getId() == receiverId) {
                recipientExists = true;
                break;
            }
        }
    }

    if (!recipientExists) {
        return false; // Recipient does not exist
    }

    // 3. Deduct cost from sender
    account[curAccount].setMoney(account[curAccount].getMoney() - cost);

    // 4. Create new expressage
    std::string newId = "KD" + std::to_string(expressageNum + 1);
    // Format ID to KD00000001 style (8 digits)
    std::string formattedId = "KD";
    std::stringstream ss_id;
    ss_id << std::setw(8) << std::setfill('0') << (expressageNum + 1);
    formattedId += ss_id.str();

    // The PRD implies the cost is transferred to the root account.
    if (rootIndex != -1) {
        account[rootIndex].setMoney(account[rootIndex].getMoney() + cost);
    }

    expressage.emplace_back(formattedId, account[curAccount].getId(), receiverId, time, "NULL", remark, false);
    expressageNum++;
    return true;
}

bool LogisticSys::signExpressage(int curAccount, const std::string& id, const std::string& time) {
    // 1. Find expressage
    auto it = std::find_if(expressage.begin(), expressage.end(), 
        [&id](const ExpressageNode& exp) { return exp.id == id; });

    if (it == expressage.end()) {
        return false; // Expressage not found
    }

    ExpressageNode& exp = *it;

    // 2. Check if current user is the recipient
    if (exp.receiveUser != account[curAccount].getId()) {
        return false; // Not the recipient
    }

    // 3. Sign it
    return exp.Sign(time);
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int curAccount) {
    std::vector<ExpressageNode> results;
    const AccountNode& currentUser = account[curAccount];
    authority userType = currentUser.getType();

    for (const auto& exp : expressage) {
        bool isSender = exp.sendUser == currentUser.getId();
        bool isRecipient = exp.receiveUser == currentUser.getId();
        bool isRootOrAdmin = (userType == root || userType == admin);

        if (isRootOrAdmin) {
            // Root and Admin can query all
            results.push_back(exp);
        } else if (isSender || isRecipient) {
            // Normal user can query if they are sender or recipient
            results.push_back(exp);
        }
    }
    return results;
}

ExpressageNode LogisticSys::queryExpressage(int curAccount, const std::string& id) {
    // This function seems to be used for specific queries (like 'q'), 
    // but the signature requires curAccount, which is unusual for a simple ID lookup.
    // We will search globally for the ID, as per the requirement "Read a logistics ID and query the package corresponding to that ID."
    for (const auto& exp : expressage) {
        if (exp.id == id) {
            return exp;
        }
    }
    // Return a default/empty node if not found
    return ExpressageNode(); 
}
