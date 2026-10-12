#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

bool LogisticSys::Regist(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad) {
    for (const auto& acc : account) {
        if (acc.id == _id) return false;
    }
    account.emplace_back(_id, _pwd, _nm, _ph, _m, _ad, authority::user);
    accountNum++;
    return true;
}

void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    std::ifstream accFile(accountFile);
    if (accFile.is_open()) {
        if (!(accFile >> accountNum)) accountNum = 0;
        account.clear();
        for (int i = 0; i < accountNum; ++i) {
            std::string id, pwd, nm, ph, ad, typeStr;
            double m;
            accFile >> id >> pwd >> nm >> ph >> m >> ad >> typeStr;
            authority t = authority::user;
            if (typeStr == "0") t = authority::root;
            else if (typeStr == "1") t = authority::admin;
            else if (typeStr == "2") t = authority::user;
            account.emplace_back(id, pwd, nm, ph, m, ad, t);
        }
        accFile.close();
    }

    std::ifstream expFile(expressageFile);
    if (expFile.is_open()) {
        if (!(expFile >> expressageNum)) expressageNum = 0;
        expressage.clear();
        for (int i = 0; i < expressageNum; ++i) {
            std::string id, sUser, rUser, aTime, sigTime, remark, statusStr;
            expFile >> id >> sUser >> rUser >> aTime >> sigTime >> statusStr >> remark;
            bool flag = (statusStr == "1");
            expressage.emplace_back(id, sUser, rUser, aTime, (sigTime == "NULL" ? "" : sigTime), remark, flag);
        }
        expFile.close();
    }

    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].type == authority::root) {
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
            accFile << acc.id << " " << acc.password << " " << acc.name << " " << acc.phone << " " 
                    << acc.money << " " << acc.address << " " << (int)acc.type << "\n";
        }
        accFile.close();
    }

    std::ofstream expFile(expressageFile);
    if (expFile.is_open()) {
        expFile << expressage.size() << "\n";
        for (const auto& exp : expressage) {
            expFile << exp.id << " " << exp.sendUser << " " << exp.receiveUser << " " 
                    << exp.assignTime << " " << (exp.signTime == "" ? "NULL" : exp.signTime) << " " 
                    << (exp.Flag ? "1" : "0") << " " << exp.remark << "\n";
        }
        expFile.close();
    }
}

int LogisticSys::Login(std::string _id, std::string _pwd) {
    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].id == _id && account[i].password == _pwd) {
            return i;
        }
    }
    return -1;
}

AccountNode LogisticSys::queryInfo(int curAccount) {
    if (curAccount >= 0 && curAccount < (int)account.size()) {
        return account[curAccount];
    }
    return AccountNode();
}

bool LogisticSys::changePassword(int curAccount, std::string oldpwd, std::string newpwd) {
    if (curAccount >= 0 && curAccount < (int)account.size()) {
        if (account[curAccount].password == oldpwd) {
            account[curAccount].password = newpwd;
            return true;
        }
    }
    return false;
}

double LogisticSys::queryMoney(int curAccount) {
    if (curAccount >= 0 && curAccount < (int)account.size()) {
        return account[curAccount].money;
    }
    return -1.0;
}

double LogisticSys::addMoney(int curAccount, double money) {
    if (curAccount >= 0 && curAccount < (int)account.size() && money >= 0) {
        account[curAccount].money += money;
        return account[curAccount].money;
    }
    return -1.0;
}

bool LogisticSys::assignExpressage(int curAccount, std::string receiverId, std::string remark, std::string time) {
    if (curAccount < 0 || curAccount >= (int)account.size()) return false;
    
    int receiverIdx = -1;
    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].id == receiverId) {
            receiverIdx = i;
            break;
        }
    }

    if (receiverIdx == -1 || receiverIdx == curAccount || receiverIdx == rootIndex) return false;
    if (account[curAccount].money < 15.0) return false;

    // Deduct money
    account[curAccount].money -= 15.0;
    if (rootIndex != -1) account[rootIndex].money += 15.0;

    // Generate ID: KD + 8 digits
    static int counter = 1;
    std::stringstream ss;
    ss << "KD" << std::setw(8) << std::setfill('0') << counter++;
    std::string newId = ss.str();

    expressage.emplace_back(newId, account[curAccount].id, receiverId, time, "NULL", remark, false);
    return true;
}

bool LogisticSys::signExpressage(int curAccount, std::string id, std::string time) {
    if (curAccount < 0 || curAccount >= (int)account.size()) return false;

    for (auto& exp : expressage) {
        if (exp.id == id && exp.receiveUser == account[curAccount].id && !exp.Flag) {
            return exp.Sign(time);
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int curAccount) {
    std::vector<ExpressageNode> result;
    if (curAccount < 0 || curAccount >= (int)account.size()) return result;

    bool isSpecial = (account[curAccount].type == authority::root || account[curAccount].type == authority::admin);

    for (const auto& exp : expressage) {
        if (isSpecial || exp.sendUser == account[curAccount].id || exp.receiveUser == account[curAccount].id) {
            result.push_back(exp);
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int curAccount, std::string id) {
    if (curAccount < 0 || curAccount >= (int)account.size()) return ExpressageNode();

    bool isSpecial = (account[curAccount].type == authority::root || account[curAccount].type == authority::admin);

    for (const auto& exp : expressage) {
        if (exp.id == id) {
            if (isSpecial || exp.sendUser == account[curAccount].id || exp.receiveUser == account[curAccount].id) {
                return exp;
            }
        }
    }
    return ExpressageNode();
}
