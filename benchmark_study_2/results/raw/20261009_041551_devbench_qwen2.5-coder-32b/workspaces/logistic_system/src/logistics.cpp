#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <vector>
#include <string>
#include "logistics.h"
#include "account.h"
#include "expressage.h"

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

bool LogisticSys::Regist(std::string id, std::string pwd, std::string name, std::string phone, double money, std::string address) {
    for (const auto& acc : account) {
        if (acc.getId() == id) {
            return false;
        }
    }
    account.emplace_back(id, pwd, name, phone, money, address, authority::user);
    accountNum++;
    return true;
}

void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    std::ifstream accountStream(accountFile);
    std::ifstream expressageStream(expressageFile);

    if (accountStream.is_open()) {
        accountStream >> accountNum;
        accountStream.ignore();
        for (int i = 0; i < accountNum; ++i) {
            std::string id, pwd, name, phone, address;
            double money;
            int type;
            std::getline(accountStream, id, ' ');
            std::getline(accountStream, pwd, ' ');
            std::getline(accountStream, name, ' ');
            std::getline(accountStream, phone, ' ');
            accountStream >> money;
            accountStream.ignore();
            std::getline(accountStream, address, ' ');
            accountStream >> type;
            accountStream.ignore();
            account.emplace_back(id, pwd, name, phone, money, address, static_cast<authority>(type));
            if (type == 0) {
                rootIndex = i;
            }
        }
        accountStream.close();
    }

    if (expressageStream.is_open()) {
        expressageStream >> expressageNum;
        expressageStream.ignore();
        for (int i = 0; i < expressageNum; ++i) {
            std::string id, sendUser, receiveUser, assignTime, signTime, remark;
            bool flag;
            std::getline(expressageStream, id, ' ');
            std::getline(expressageStream, sendUser, ' ');
            std::getline(expressageStream, receiveUser, ' ');
            std::getline(expressageStream, assignTime, ' ');
            std::getline(expressageStream, signTime, ' ');
            expressageStream >> flag;
            expressageStream.ignore();
            std::getline(expressageStream, remark);
            expressage.emplace_back(id, sendUser, receiveUser, assignTime, signTime, remark, flag);
        }
        expressageStream.close();
    }
}

void LogisticSys::save(std::string accountFile, std::string expressageFile) {
    std::ofstream accountStream(accountFile);
    std::ofstream expressageStream(expressageFile);

    if (accountStream.is_open()) {
        accountStream << accountNum << "\n";
        for (const auto& acc : account) {
            accountStream << acc;
        }
        accountStream.close();
    }

    if (expressageStream.is_open()) {
        expressageStream << expressageNum << "\n";
        for (const auto& exp : expressage) {
            expressageStream << exp;
        }
        expressageStream.close();
    }
}

int LogisticSys::Login(std::string id, std::string pwd) {
    for (int i = 0; i < accountNum; ++i) {
        if (account[i].getId() == id && account[i].getPassword() == pwd) {
            return i;
        }
    }
    return -1;
}

AccountNode LogisticSys::queryInfo(int index) {
    return account[index];
}

bool LogisticSys::changePassword(int index, std::string oldPwd, std::string newPwd) {
    if (account[index].getPassword() == oldPwd) {
        account[index].setPassword(newPwd);
        return true;
    }
    return false;
}

double LogisticSys::queryMoney(int index) {
    return account[index].getMoney();
}

double LogisticSys::addMoney(int index, double amount) {
    account[index].setMoney(account[index].getMoney() + amount);
    return account[index].getMoney();
}

bool LogisticSys::assignExpressage(int index, std::string receiverId, std::string remark, std::string time) {
    if (account[index].getMoney() < 15) {
        return false;
    }
    for (const auto& acc : account) {
        if (acc.getId() == receiverId && acc.getId() != account[rootIndex].getId() && acc.getMoney() >= 0) {
            account[index].setMoney(account[index].getMoney() - 15);
            account[rootIndex].setMoney(account[rootIndex].getMoney() + 15);
            std::ostringstream oss;
            oss << "KD" << std::setw(8) << std::setfill('0') << expressageNum + 1;
            std::string newId = oss.str();
            expressage.emplace_back(newId, account[index].getId(), receiverId, time, "NULL", remark, false);
            expressageNum++;
            return true;
        }
    }
    return false;
}

bool LogisticSys::signExpressage(int index, std::string expressageId, std::string time) {
    for (auto& exp : expressage) {
        if (exp.getReceiveUser() == account[index].getId() && exp.getId() == expressageId) {
            exp.Sign(time);
            return true;
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int index) {
    std::vector<ExpressageNode> result;
    if (account[index].getType() == authority::root || account[index].getType() == authority::admin) {
        return expressage;
    }
    for (const auto& exp : expressage) {
        if (exp.getSendUser() == account[index].getId() || exp.getReceiveUser() == account[index].getId()) {
            result.push_back(exp);
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int index, std::string expressageId) {
    for (const auto& exp : expressage) {
        if (exp.getId() == expressageId && (exp.getSendUser() == account[index].getId() || exp.getReceiveUser() == account[index].getId())) {
            return exp;
        }
    }
    return ExpressageNode();
}
