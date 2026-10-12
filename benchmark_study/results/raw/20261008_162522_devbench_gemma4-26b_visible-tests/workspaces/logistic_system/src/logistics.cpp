#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    std::ifstream accFile(accountFile);
    if (accFile.is_open()) {
        if (!(accFile >> accountNum)) accountNum = 0;
        for (int i = 0; i < accountNum; ++i) {
            std::string id, pwd, name, phone, address;
            double money;
            int typeInt;
            accFile >> id >> pwd >> name >> phone >> money >> address >> typeInt;
            account.emplace_back(id, pwd, name, phone, money, address, static_cast<authority>(typeInt));
        }
        accFile.close();
    }

    std::ifstream expFile(expressageFile);
    if (expFile.is_open()) {
        if (!(expFile >> expressageNum)) expressageNum = 0;
        for (int i = 0; i < expressageNum; ++i) {
            std::string id, sender, receiver, sendTime, signTime, remark, statusStr;
            int status;
            expFile >> id >> sender >> receiver >> sendTime >> signTime >> status >> remark;
            bool flag = (status == 1);
            expressage.emplace_back(id, sender, receiver, sendTime, signTime, remark, flag);
        }
        expFile.close();
    }

    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].getType() == root) {
            rootIndex = i;
            break;
        }
    }
}

void LogisticSys::save(std::string accountFile, std::string expressageFile) {
    std::ofstream accFile(accountFile);
    if (accFile.is_open()) {
        accFile << account.size() << "\n";
        for (const auto& acc : account) {
            accFile << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " "
                    << acc.getPhone() << " " << acc.getMoney() << " "
                    << acc.getAddress() << " " << static_cast<int>(acc.getType()) << "\n";
        }
        accFile.close();
    }

    std::ofstream expFile(expressageFile);
    if (expFile.is_open()) {
        expFile << expressage.size() << "\n";
        for (const auto& exp : expressage) {
            int status = exp.getFlag() ? 1 : 0;
            expFile << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " "
                    << exp.getAssignTime() << " " << (exp.getFlag() ? exp.getSignTime() : "NULL") << " "
                    << status << " " << exp.getRemark() << "\n";
        }
        expFile.close();
    }
}

bool LogisticSys::Regist(std::string id, std::string pwd, std::string name, std::string phone, double money, std::string address) {
    for (const auto& acc : account) {
        if (acc.getId() == id) return false;
    }
    account.emplace_back(id, pwd, name, phone, money, address, user);
    return true;
}

int LogisticSys::Login(std::string id, std::string pwd) {
    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].getId() == id && account[i].getPassword() == pwd) {
            return i;
        }
    }
    return -1;
}

AccountNode LogisticSys::queryInfo(int index) {
    if (index >= 0 && index < (int)account.size()) {
        return account[index];
    }
    return AccountNode();
}

bool LogisticSys::changePassword(int index, std::string opwd, std::string npwd) {
    if (index >= 0 && index < (int)account.size()) {
        if (account[index].getPassword() == opwd) {
            account[index].setPassword(npwd);
            return true;
        }
    }
    return false;
}

double LogisticSys::queryMoney(int index) {
    if (index >= 0 && index < (int)account.size()) {
        return account[index].getMoney();
    }
    return -1.0;
}

double LogisticSys::addMoney(int index, double amount) {
    if (index < 0 || index >= (int)account.size()) {
        return -1.0;
    }
    if (amount < 0) {
        return 0.0;
    }
    account[index].setMoney(account[index].getMoney() + amount);
    return account[index].getMoney();
}

bool LogisticSys::assignExpressage(int senderIndex, std::string receiverId, std::string remark, std::string time) {
    if (senderIndex < 0 || senderIndex >= (int)account.size()) return false;
    
    int receiverIndex = -1;
    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].getId() == receiverId) {
            receiverIndex = i;
            break;
        }
    }

    // If receiver doesn't exist, return false
    if (receiverIndex == -1) return false;

    // Check if receiver is the sender
    if (receiverId == account[senderIndex].getId()) return false;

    // Check if receiver is root
    if (rootIndex != -1 && receiverIndex == rootIndex) return false;

    // Check if sender has enough money
    if (account[senderIndex].getMoney() < 15.0) return false;

    // Deduct 15 from sender, add to root
    account[senderIndex].setMoney(account[senderIndex].getMoney() - 15.0);
    if (rootIndex != -1) {
        account[rootIndex].setMoney(account[rootIndex].getMoney() + 15.0);
    }

    // Generate ID: KD + 8 digits
    std::stringstream ss;
    ss << "KD" << std::setw(8) << std::setfill('0') << (expressage.size() + 1);
    std::string newId = ss.str();

    expressage.emplace_back(newId, account[senderIndex].getId(), account[receiverIndex].getId(), time, "NULL", remark, false);
    return true;
}

bool LogisticSys::signExpressage(int receiverIndex, std::string expressageId, std::string time) {
    if (receiverIndex < 0 || receiverIndex >= (int)account.size()) return false;

    for (auto& exp : expressage) {
        if (exp.getId() == expressageId && exp.getReceiveUser() == account[receiverIndex].getId() && !exp.getFlag()) {
            exp.Sign(time);
            return true;
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int index) {
    std::vector<ExpressageNode> result;
    if (index < 0 || index >= (int)account.size()) return result;
    
    authority userType = account[index].getType();

    for (const auto& exp : expressage) {
        if (userType == root || userType == admin) {
            result.push_back(exp);
        } else {
            if (exp.getSendUser() == account[index].getId() || exp.getReceiveUser() == account[index].getId()) {
                result.push_back(exp);
            }
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int index, std::string expressageId) {
    if (index < 0 || index >= (int)account.size()) return ExpressageNode();

    for (const auto& exp : expressage) {
        if (exp.getId() == expressageId) {
            authority userType = account[index].getType();
            if (userType == root || userType == admin || 
                exp.getSendUser() == account[index].getId() || 
                exp.getReceiveUser() == account[index].getId()) {
                return exp;
            }
        }
    }
    return ExpressageNode(); 
}
