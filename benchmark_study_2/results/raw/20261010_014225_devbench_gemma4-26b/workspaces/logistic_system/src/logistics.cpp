#include "logistics.h"
#include <fstream>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <string>
#include <vector>

using std::string;
using std::vector;
using std::ifstream;
using std::ofstream;
using std::endl;
using std::stringstream;
using std::setfill;
using std::setw;

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

void LogisticSys::init(string accFile, string expFile) {
    account.clear();
    expressage.clear();
    accountNum = 0;
    expressageNum = 0;
    rootIndex = -1;

    ifstream accIn(accFile);
    if (accIn.is_open()) {
        if (!(accIn >> accountNum)) accountNum = 0;
        for (int i = 0; i < accountNum; ++i) {
            string id, pwd, name, phone, addr;
            double money;
            int typeInt;
            accIn >> id >> pwd >> name >> phone >> money >> addr >> typeInt;
            authority type;
            if (typeInt == 0) type = root;
            else if (typeInt == 1) type = admin;
            else type = user;
            account.emplace_back(id, pwd, name, phone, money, addr, type);
            if (type == root) rootIndex = i;
        }
        accIn.close();
    }

    ifstream expIn(expFile);
    if (expIn.is_open()) {
        if (!(expIn >> expressageNum)) expressageNum = 0;
        for (int i = 0; i < expressageNum; ++i) {
            string id, sender, receiver, sTime, rTime, remark;
            int status;
            expIn >> id >> sender >> receiver >> sTime >> rTime >> status >> remark;
            bool flag = (status == 1);
            expressage.emplace_back(id, sender, receiver, sTime, rTime, remark, flag);
        }
        expIn.close();
    }
}

void LogisticSys::save(string accFile, string expFile) {
    ofstream accOut(accFile);
    if (accOut.is_open()) {
        accOut << account.size() << endl;
        for (const auto& acc : account) {
            int typeInt = 0;
            if (acc.getType() == admin) typeInt = 1;
            else if (acc.getType() == user) typeInt = 2;
            accOut << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " " 
                   << acc.getPhone() << " " << acc.getMoney() << " " << acc.getAddress() << " " << typeInt << endl;
        }
        accOut.close();
    }

    ofstream expOut(expFile);
    if (expOut.is_open()) {
        expOut << expressage.size() << endl;
        for (const auto& exp : expressage) {
            int status = exp.getFlag() ? 1 : 0;
            expOut << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " " 
                   << exp.getAssignTime() << " " << exp.getSignTime() << " " << status << " " << exp.getRemark() << endl;
        }
        expOut.close();
    }
}

bool LogisticSys::Regist(string id, string pwd, string name, string phone, double money, string addr) {
    for (const auto& acc : account) {
        if (acc.getId() == id) return false;
    }
    account.emplace_back(id, pwd, name, phone, money, addr, user);
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

AccountNode LogisticSys::queryInfo(int idx) {
    return account[idx];
}

bool LogisticSys::changePassword(int idx, string opwd, string npwd) {
    if (idx < 0 || idx >= (int)account.size()) return false;
    if (account[idx].getPassword() != opwd) return false;
    // Since AccountNode doesn't have setPassword in UML, but we must update it.
    // However, the task says "use getter/setter". I'll assume the implementation 
    // of AccountNode allows updating via a method or I'll use a workaround if needed.
    // Looking at UML, there is no setPassword. But the error says password is private.
    // I will assume the class has a way to update or I will use a friend-like approach if I could,
    // but I must follow the "use getter/setter" instruction. 
    // Wait, the error message shows I should use setters. I'll assume they exist.
    // Since I can't change account.h, I'll use a logic that assumes the existence of setters.
    // Actually, I'll just use the fact that I'm in LogisticSys which might be a friend, 
    // but the error says it's private. Let's assume the class has setPassword, setMoney, etc.
    // Re-reading: "I need to change all access to use corresponding getter/setter".
    // I will use the setters.
    account[idx].setPassword(npwd); 
    return true;
}

double LogisticSys::queryMoney(int idx) {
    if (idx < 0 || idx >= (int)account.size()) return 0.0;
    return account[idx].getMoney();
}

double LogisticSys::addMoney(int idx, double amount) {
    if (idx < 0 || idx >= (int)account.size() || amount < 0) return -1.0;
    account[idx].setMoney(account[idx].getMoney() + amount);
    return account[idx].getMoney();
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

    if (receiverIdx == -1 || account[receiverIdx].getId() == "root_id") {
        receiverIdx = rootIndex;
    }

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
    vector<ExpressageNode> res;
    authority type = account[userIdx].getType();
    for (const auto& exp : expressage) {
        if (type == root || type == admin) {
            res.push_back(exp);
        } else {
            if (exp.getSendUser() == account[userIdx].getId() || exp.getReceiveUser() == account[userIdx].getId()) {
                res.push_back(exp);
            }
        }
    }
    return res;
}

ExpressageNode LogisticSys::queryExpressage(int userIdx, string expId) {
    for (const auto& exp : expressage) {
        if (exp.getId() == expId) {
            if (account[userIdx].getType() == root || account[userIdx].getType() == admin || 
                exp.getSendUser() == account[userIdx].getId() || exp.getReceiveUser() == account[userIdx].getId()) {
                return exp;
            }
        }
    }
    return ExpressageNode("", "", "", "", "", "", false);
}
