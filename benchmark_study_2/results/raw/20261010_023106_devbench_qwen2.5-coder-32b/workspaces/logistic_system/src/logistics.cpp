#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <vector>
#include <string>
#include "logistics.h"

using namespace std;

// LogisticSys methods
LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

void LogisticSys::init(string accountFile, string expressageFile) {
    ifstream accountStream(accountFile);
    ifstream expressageStream(expressageFile);

    if (accountStream.is_open()) {
        accountStream >> accountNum;
        for (int i = 0; i < accountNum; ++i) {
            string id, password, name, phone, address;
            double money;
            int type;
            accountStream >> id >> password >> name >> phone >> money >> address >> type;
            account.emplace_back(id, password, name, phone, money, address, static_cast<authority>(type));
            if (type == static_cast<int>(authority::root)) rootIndex = i;
        }
        accountStream.close();
    }

    if (expressageStream.is_open()) {
        expressageStream >> expressageNum;
        for (int i = 0; i < expressageNum; ++i) {
            string id, sendUser, receiveUser, assignTime, signTime, remark;
            bool Flag;
            expressageStream >> id >> sendUser >> receiveUser >> assignTime >> signTime >> Flag >> remark;
            expressage.emplace_back(id, sendUser, receiveUser, assignTime, signTime, remark, Flag);
        }
        expressageStream.close();
    }
}

void LogisticSys::save(string accountFile, string expressageFile) {
    ofstream accountStream(accountFile);
    ofstream expressageStream(expressageFile);

    if (accountStream.is_open()) {
        accountStream << accountNum << "\n";
        for (const auto& acc : account) {
            accountStream << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " " << acc.getPhone() << " "
                          << fixed << setprecision(2) << acc.getMoney() << " " << acc.getAddress() << " " << static_cast<int>(acc.getType()) << "\n";
        }
        accountStream.close();
    }

    if (expressageStream.is_open()) {
        expressageStream << expressageNum << "\n";
        for (const auto& exp : expressage) {
            expressageStream << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " " << exp.getAssignTime() << " "
                             << (exp.getSignTime().empty() ? "NULL" : exp.getSignTime()) << " " << exp.isFlag() << " " << exp.getRemark() << "\n";
        }
        expressageStream.close();
    }
}

bool LogisticSys::Regist(string id, string password, string name, string phone, double money, string address) {
    for (const auto& acc : account) {
        if (acc.getId() == id) return false;
    }
    account.emplace_back(id, password, name, phone, money, address, authority::normal_user);
    accountNum++;
    return true;
}

int LogisticSys::Login(string id, string password) {
    for (int i = 0; i < accountNum; ++i) {
        if (account[i].getId() == id && account[i].getPassword() == password) {
            return i;
        }
    }
    return -1;
}

AccountNode LogisticSys::queryInfo(int index) {
    return account[index];
}

bool LogisticSys::changePassword(int index, string oldPassword, string newPassword) {
    if (account[index].getPassword() == oldPassword) {
        account[index].setPassword(newPassword);
        return true;
    }
    return false;
}

double LogisticSys::queryMoney(int index) {
    return account[index].getMoney();
}

double LogisticSys::addMoney(int index, double amount) {
    if (amount < 0) return -1;
    account[index].addMoney(amount);
    return account[index].getMoney();
}

bool LogisticSys::assignExpressage(int index, string receiverId, string remark, string time) {
    for (auto& acc : account) {
        if (acc.getId() == receiverId && acc.getId() != account[index].getId() && acc.getMoney() >= 15) {
            acc.addMoney(-15);
            account[rootIndex].addMoney(15);
            expressage.emplace_back("KD" + to_string(expressageNum + 1).substr(0, 8), account[index].getId(), receiverId, time, "", remark, false);
            expressageNum++;
            return true;
        }
    }
    return false;
}

bool LogisticSys::signExpressage(int index, string expressageId, string time) {
    for (auto& exp : expressage) {
        if (exp.getId() == expressageId && exp.getReceiveUser() == account[index].getId()) {
            return exp.Sign(time);
        }
    }
    return false;
}

vector<ExpressageNode> LogisticSys::queryAllExpressage(int index) {
    vector<ExpressageNode> result;
    for (const auto& exp : expressage) {
        if (account[index].getType() == authority::root || exp.getSendUser() == account[index].getId() || exp.getReceiveUser() == account[index].getId()) {
            result.push_back(exp);
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int index, string expressageId) {
    for (const auto& exp : expressage) {
        if (exp.getId() == expressageId && (account[index].getType() == authority::root || exp.getSendUser() == account[index].getId() || exp.getReceiveUser() == account[index].getId())) {
            return exp;
        }
    }
    return ExpressageNode();
}
