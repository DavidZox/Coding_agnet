#include "logistics.h"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include <string>
#include <vector>

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    std::ifstream accFile(accountFile);
    if (accFile.is_open()) {
        if (!(accFile >> accountNum)) accountNum = 0;
        for (int i = 0; i < accountNum; ++i) {
            std::string id, pwd, name, phone, addr;
            double money;
            int typeInt;
            accFile >> id >> pwd >> name >> phone >> money >> addr >> typeInt;
            authority type = static_cast<authority>(typeInt);
            account.emplace_back(id, pwd, name, phone, money, addr, type);
            if (type == authority::root) {
                rootIndex = i;
            }
        }
        accFile.close();
    }

    std::ifstream expFile(expressageFile);
    if (expFile.is_open()) {
        if (!(expFile >> expressageNum)) expressageNum = 0;
        std::string dummy;
        std::getline(expFile, dummy); // consume newline after expressageNum
        for (int i = 0; i < expressageNum; ++i) {
            std::string line;
            if (std::getline(expFile, line)) {
                std::stringstream ss(line);
                std::string id, sender, receiver, sTime, rTime, remark;
                int status;
                ss >> id >> sender >> receiver >> sTime >> rTime >> status;
                // The rest of the line is the remark, which might contain spaces
                std::getline(ss >> std::ws, remark);
                
                bool flag = (status == 1);
                expressage.emplace_back(id, sender, receiver, sTime, rTime, remark, flag);
            }
        }
        expFile.close();
    }
}

void LogisticSys::save(std::string accountFile, std::string expressageFile) {
    std::ofstream accFile(accountFile);
    if (accFile.is_open()) {
        accFile << account.size() << std::endl;
        for (const auto& acc : account) {
            accFile << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " " 
                    << acc.getPhone() << " " << acc.getMoney() << " " << acc.getAddress() << " " 
                    << static_cast<int>(acc.getType()) << std::endl;
        }
        accFile.close();
    }

    std::ofstream expFile(expressageFile);
    if (expFile.is_open()) {
        expFile << expressage.size() << std::endl;
        for (const auto& exp : expressage) {
            expFile << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " " 
                    << exp.getAssignTime() << " " << exp.getSignTime() << " " 
                    << (exp.getFlag() ? 1 : 0) << " " << exp.getRemark() << std::endl;
        }
        expFile.close();
    }
}

bool LogisticSys::Regist(std::string id, std::string pwd, std::string name, std::string phone, double money, std::string addr) {
    for (const auto& acc : account) {
        if (acc.getId() == id) return false;
    }
    account.emplace_back(id, pwd, name, phone, money, addr, authority::normal_user);
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
    if (index >= 0 && index < (int)account.size() && account[index].getPassword() == opwd) {
        account[index].setPassword(npwd);
        return true;
    }
    return false;
}

double LogisticSys::queryMoney(int index) {
    if (index >= 0 && index < (int)account.size()) {
        return account[index].getMoney();
    }
    return 0.0;
}

double LogisticSys::addMoney(int index, double amount) {
    if (index >= 0 && index < (int)account.size() && amount >= 0) {
        double new_money = account[index].getMoney() + amount;
        account[index].setMoney(new_money);
        return new_money;
    }
    return -1.0;
}

bool LogisticSys::assignExpressage(int senderIdx, std::string receiverId, std::string remark, std::string time) {
    if (senderIdx < 0 || senderIdx >= (int)account.size()) return false;
    
    int receiverIdx = -1;
    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].getId() == receiverId) {
            receiverIdx = i;
            break;
        }
    }

    // If recipient doesn't exist or is root, recipient is root
    if (receiverIdx == -1 || account[receiverIdx].getType() == authority::root) {
        receiverIdx = rootIndex;
    }

    // Check if sender has enough money (15 units)
    if (account[senderIdx].getMoney() < 15.0) return false;

    // Deduct 15 from sender, add to root
    account[senderIdx].setMoney(account[senderIdx].getMoney() - 15.0);
    if (rootIndex != -1) {
        account[rootIndex].setMoney(account[rootIndex].getMoney() + 15.0);
    }

    std::string newId = "KD";
    int nextNum = (int)expressage.size() + 1;
    std::stringstream ss;
    ss << std::setfill('0') << std::setw(8) << nextNum;
    newId += ss.str();

    expressage.emplace_back(newId, account[senderIdx].getId(), account[receiverIdx].getId(), time, "NULL", remark, false);
    return true;
}

bool LogisticSys::signExpressage(int userIdx, std::string expId, std::string time) {
    if (userIdx < 0 || userIdx >= (int)account.size()) return false;

    for (auto& exp : expressage) {
        if (exp.getId() == expId && exp.getReceiveUser() == account[userIdx].getId() && !exp.getFlag()) {
            exp.Sign(time);
            return true;
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int userIdx) {
    std::vector<ExpressageNode> result;
    if (userIdx < 0 || userIdx >= (int)account.size()) return result;

    authority type = account[userIdx].getType();
    std::string uid = account[userIdx].getId();

    for (const auto& exp : expressage) {
        if (type == authority::root || type == authority::admin) {
            result.push_back(exp);
        } else {
            if (exp.getSendUser() == uid || exp.getReceiveUser() == uid) {
                result.push_back(exp);
            }
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int userIdx, std::string expId) {
    // The requirement says "query the package corresponding to that ID"
    // Usually, this implies searching globally, but the signature takes userIdx.
    // Based on typical logic, we search all expressages for the ID.
    for (const auto& exp : expressage) {
        if (exp.getId() == expId) {
            return exp;
        }
    }
    return ExpressageNode();
}

// Additional helper methods for specific query types
std::vector<ExpressageNode> LogisticSys::queryAlls(int userIdx) {
    std::vector<ExpressageNode> result;
    std::string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getSendUser() == uid) result.push_back(exp);
    }
    return result;
}

std::vector<ExpressageNode> LogisticSys::queryAllr(int userIdx) {
    std::vector<ExpressageNode> result;
    std::string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getReceiveUser() == uid) result.push_back(exp);
    }
    return result;
}

std::vector<ExpressageNode> LogisticSys::queryBySender(int userIdx, std::string x) {
    std::vector<ExpressageNode> result;
    std::string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getSendUser() == x && (exp.getSendUser() == uid || exp.getReceiveUser() == uid)) {
            result.push_back(exp);
        }
    }
    return result;
}

std::vector<ExpressageNode> LogisticSys::queryByReceiver(int userIdx, std::string x) {
    std::vector<ExpressageNode> result;
    std::string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getReceiveUser() == x && (exp.getSendUser() == uid || exp.getReceiveUser() == uid)) {
            result.push_back(exp);
        }
    }
    return result;
}

std::vector<ExpressageNode> LogisticSys::queryByTime(int userIdx, std::string t) {
    std::vector<ExpressageNode> result;
    std::string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getAssignTime() == t && (exp.getSendUser() == uid || exp.getReceiveUser() == uid)) {
            result.push_back(exp);
        }
    }
    return result;
}
