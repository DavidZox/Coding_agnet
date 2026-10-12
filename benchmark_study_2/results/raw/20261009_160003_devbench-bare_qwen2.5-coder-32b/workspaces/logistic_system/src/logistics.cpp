#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iomanip>

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

bool LogisticSys::Regist(const std::string& _id, const std::string& _pwd, const std::string& _nm, const std::string& _ph, double _m, const std::string& _ad) {
    for (const auto& acc : account) {
        if (acc.id == _id) {
            return false;
        }
    }
    account.emplace_back(_id, _pwd, _nm, _ph, _m, _ad, authority::user);
    accountNum++;
    return true;
}

void LogisticSys::init(const std::string& accountFile, const std::string& expressageFile) {
    std::ifstream accountStream(accountFile);
    std::ifstream expressageStream(expressageFile);

    if (accountStream.is_open()) {
        accountStream >> accountNum;
        accountStream.ignore();
        for (int i = 0; i < accountNum; ++i) {
            std::string _id, _pwd, _nm, _ph, _ad;
            double _m;
            int _t;
            std::getline(accountStream, _id, ' ');
            std::getline(accountStream, _pwd, ' ');
            std::getline(accountStream, _nm, ' ');
            std::getline(accountStream, _ph, ' ');
            accountStream >> _m;
            accountStream.ignore();
            std::getline(accountStream, _ad, ' ');
            accountStream >> _t;
            accountStream.ignore();
            account.emplace_back(_id, _pwd, _nm, _ph, _m, _ad, static_cast<authority>(_t));
            if (_t == 0) {
                rootIndex = i;
            }
        }
    }

    if (expressageStream.is_open()) {
        expressageStream >> expressageNum;
        expressageStream.ignore();
        for (int i = 0; i < expressageNum; ++i) {
            std::string _id, _sendUser, _receiveUser, _assignTime, _signTime, _remark;
            bool _Flag;
            std::getline(expressageStream, _id, ' ');
            std::getline(expressageStream, _sendUser, ' ');
            std::getline(expressageStream, _receiveUser, ' ');
            std::getline(expressageStream, _assignTime, ' ');
            std::getline(expressageStream, _signTime, ' ');
            std::getline(expressageStream, _remark, ' ');
            expressageStream >> _Flag;
            expressageStream.ignore();
            expressage.emplace_back(_id, _sendUser, _receiveUser, _assignTime, _signTime, _remark, _Flag);
        }
    }
}

void LogisticSys::save(const std::string& accountFile, const std::string& expressageFile) {
    std::ofstream accountStream(accountFile);
    std::ofstream expressageStream(expressageFile);

    if (accountStream.is_open()) {
        accountStream << accountNum << "\n";
        for (const auto& acc : account) {
            accountStream << acc.id << " " << acc.password << " " << acc.name << " " << acc.phone << " " << acc.money << " " << acc.address << " " << static_cast<int>(acc.type) << "\n";
        }
    }

    if (expressageStream.is_open()) {
        expressageStream << expressageNum << "\n";
        for (const auto& exp : expressage) {
            expressageStream << exp.id << " " << exp.sendUser << " " << exp.receiveUser << " " << exp.assignTime << " " << exp.signTime << " " << exp.remark << " " << exp.Flag << "\n";
        }
    }
}

int LogisticSys::Login(const std::string& _id, const std::string& _pwd) {
    for (int i = 0; i < accountNum; ++i) {
        if (account[i].id == _id && account[i].password == _pwd) {
            return i;
        }
    }
    return -1;
}

AccountNode LogisticSys::queryInfo(int curAccount) {
    return account[curAccount];
}

bool LogisticSys::changePassword(int curAccount, const std::string& oldpwd, const std::string& newpwd) {
    if (account[curAccount].password == oldpwd) {
        account[curAccount].password = newpwd;
        return true;
    }
    return false;
}

double LogisticSys::queryMoney(int curAccount) {
    return account[curAccount].money;
}

double LogisticSys::addMoney(int curAccount, double money) {
    account[curAccount].money += money;
    return account[curAccount].money;
}

bool LogisticSys::assignExpressage(int curAccount, const std::string& receiverId, const std::string& remark, const std::string& time) {
    if (account[curAccount].money < 15.0) {
        return false;
    }
    for (const auto& acc : account) {
        if (acc.id == receiverId && acc.id != account[curAccount].id && acc.money >= 0) {
            account[curAccount].money -= 15.0;
            account[rootIndex].money += 15.0;
            std::ostringstream idStream;
            idStream << "KD" << std::setw(8) << std::setfill('0') << expressageNum + 1;
            expressage.emplace_back(idStream.str(), account[curAccount].id, receiverId, time, "NULL", remark, false);
            expressageNum++;
            return true;
        }
    }
    return false;
}

bool LogisticSys::signExpressage(int curAccount, const std::string& id, const std::string& time) {
    for (auto& exp : expressage) {
        if (exp.id == id && exp.receiveUser == account[curAccount].id && !exp.Flag) {
            exp.Sign(time);
            return true;
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int curAccount) {
    std::vector<ExpressageNode> result;
    for (const auto& exp : expressage) {
        if (account[curAccount].type == authority::root || account[curAccount].type == authority::admin ||
            exp.sendUser == account[curAccount].id || exp.receiveUser == account[curAccount].id) {
            result.push_back(exp);
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int curAccount, const std::string& id) {
    for (const auto& exp : expressage) {
        if (exp.id == id && (account[curAccount].type == authority::root || account[curAccount].type == authority::admin ||
                             exp.sendUser == account[curAccount].id || exp.receiveUser == account[curAccount].id)) {
            return exp;
        }
    }
    return ExpressageNode();
}
