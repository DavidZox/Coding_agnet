#include "logistics.h"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <algorithm>

using namespace std;

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

void LogisticSys::init(string accountFile, string expressageFile) {
    ifstream accFile(accountFile);
    if (accFile.is_open()) {
        if (!(accFile >> accountNum)) accountNum = 0;
        for (int i = 0; i < accountNum; ++i) {
            string id, pwd, name, phone, address;
            double money;
            int typeInt;
            accFile >> id >> pwd >> name >> phone >> money >> address >> typeInt;
            authority type = static_cast<authority>(typeInt);
            account.emplace_back(id, pwd, name, phone, money, address, type);
            if (type == authority::root) {
                rootIndex = i;
            }
        }
        accFile.close();
    }

    ifstream expFile(expressageFile);
    if (expFile.is_open()) {
        if (!(expFile >> expressageNum)) expressageNum = 0;
        for (int i = 0; i < expressageNum; ++i) {
            string id, sendUser, receiveUser, assignTime, signTime, remark, statusStr;
            int status;
            expFile >> id >> sendUser >> receiveUser >> assignTime >> signTime >> status >> remark;
            bool flag = (status == 1);
            expressage.emplace_back(id, sendUser, receiveUser, assignTime, signTime, remark, flag);
        }
        expFile.close();
    }
}

void LogisticSys::save(string accountFile, string expressageFile) {
    ofstream accFile(accountFile);
    if (accFile.is_open()) {
        accFile << account.size() << endl;
        for (const auto& acc : account) {
            accFile << acc.getId() << " " 
                    << acc.getPassword() << " " 
                    << acc.getName() << " " 
                    << acc.getPhone() << " " 
                    << fixed << setprecision(0) << acc.getMoney() << " " 
                    << acc.getAddress() << " " 
                    << static_cast<int>(acc.getType()) << endl;
        }
        accFile.close();
    }

    ofstream expFile(expressageFile);
    if (expFile.is_open()) {
        expFile << expressage.size() << endl;
        for (const auto& exp : expressage) {
            int status = exp.getFlag() ? 1 : 0;
            expFile << exp.getId() << " " 
                    << exp.getSendUser() << " " 
                    << exp.getReceiveUser() << " " 
                    << exp.getAssignTime() << " " 
                    << (exp.getSignTime() == "NULL" ? "NULL" : exp.getSignTime()) << " " 
                    << status << " " 
                    << exp.getRemark() << endl;
        }
        expFile.close();
    }
}

bool LogisticSys::Regist(string id, string pwd, string name, string phone, double money, string address) {
    for (const auto& acc : account) {
        if (acc.getId() == id) return false;
    }
    account.emplace_back(id, pwd, name, phone, money, address, authority::user);
    return true;
}

int LogisticSys::Login(string id, string pwd) {
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

bool LogisticSys::changePassword(int index, string opwd, string npwd) {
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
    return 0.0;
}

double LogisticSys::addMoney(int index, double amount) {
    if (index >= 0 && index < (int)account.size() && amount >= 0) {
        account[index].setMoney(account[index].getMoney() + amount);
        return account[index].getMoney();
    }
    return -1.0;
}

bool LogisticSys::assignExpressage(int senderIdx, string receiverId, string remark, string time) {
    if (senderIdx < 0 || senderIdx >= (int)account.size()) return false;
    
    int receiverIdx = -1;
    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].getId() == receiverId) {
            receiverIdx = i;
            break;
        }
    }

    if (receiverIdx == -1 || account[receiverIdx].getId() == "root_id" || account[receiverIdx].getType() == authority::root) {
        receiverIdx = rootIndex;
    }

    if (receiverIdx == -1 || account[receiverIdx].getMoney() < 0) return false; 
    if (account[senderIdx].getMoney() < 15.0) return false;

    account[senderIdx].setMoney(account[senderIdx].getMoney() - 15.0);
    if (rootIndex != -1) {
        account[rootIndex].setMoney(account[rootIndex].getMoney() + 15.0);
    }

    string newId = "KD";
    int nextNum = expressage.size() + 1;
    stringstream ss;
    ss << setfill('0') << setw(8) << nextNum;
    newId += ss.str();

    expressage.emplace_back(newId, account[senderIdx].getId(), account[receiverIdx].getId(), time, "NULL", remark, false);
    return true;
}

bool LogisticSys::signExpressage(int userIdx, string expId, string time) {
    if (userIdx < 0 || userIdx >= (int)account.size()) return false;
    for (auto& exp : expressage) {
        if (exp.getId() == expId && exp.getReceiveUser() == account[userIdx].getId() && !exp.getFlag()) {
            exp.Sign(time);
            return true;
        }
    }
    return false;
}

vector<ExpressageNode> LogisticSys::queryAllExpressage(int userIdx) {
    vector<ExpressageNode> result;
    if (userIdx < 0 || userIdx >= (int)account.size()) return result;

    bool isPrivileged = (account[userIdx].getType() == authority::root || account[userIdx].getType() == authority::admin);
    string myId = account[userIdx].getId();

    for (const auto& exp : expressage) {
        if (isPrivileged || exp.getSendUser() == myId || exp.getReceiveUser() == myId) {
            result.push_back(exp);
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int userIdx, string expId) {
    string myId = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getId() == expId && (exp.getSendUser() == myId || exp.getReceiveUser() == myId)) {
            return exp;
        }
    }
    return ExpressageNode();
}
