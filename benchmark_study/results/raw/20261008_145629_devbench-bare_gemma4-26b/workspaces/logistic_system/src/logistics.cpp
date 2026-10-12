#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

bool LogisticSys::Regist(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad) {
    for (const auto& acc : account) {
        if (acc.getId() == _id) return false;
    }
    account.emplace_back(_id, _pwd, _nm, _ph, _m, _ad, authority::user);
    accountNum++;
    return true;
}

void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    std::ifstream accFile(accountFile);
    if (accFile.is_open()) {
        int n;
        accFile >> n;
        account.clear();
        for (int i = 0; i < n; ++i) {
            std::string id, pwd, name, phone, address;
            double money;
            int typeInt;
            accFile >> id >> pwd >> name >> phone >> money >> address >> typeInt;
            authority type = static_cast<authority>(typeInt);
            account.emplace_back(id, pwd, name, phone, money, address, type);
        }
        accountNum = account.size();
        for (int i = 0; i < accountNum; ++i) {
            if (account[i].getType() == authority::root) rootIndex = i;
        }
        accFile.close();
    }

    std::ifstream expFile(expressageFile);
    if (expFile.is_open()) {
        int m;
        expFile >> m;
        expressage.clear();
        for (int i = 0; i < m; ++i) {
            std::string id, sender, receiver, assignTime, signTime, remark, statusStr;
            int status;
            expFile >> id >> sender >> receiver >> assignTime >> signTime >> status >> remark;
            bool flag = (status == 1);
            expressage.emplace_back(id, sender, receiver, assignTime, signTime, remark, flag);
        }
        expressageNum = expressage.size();
        expFile.close();
    }
}

void LogisticSys::save(std::string accountFile, std::string expressageFile) {
    std::ofstream accFile(accountFile);
    if (accFile.is_open()) {
        accFile << account.size() << "\n";
        for (const auto& acc : account) {
            accFile << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " "
                    << acc.getPhone() << " " << acc.getMoney() << " " << acc.getAddress() << " "
                    << static_cast<int>(acc.getType()) << "\n";
        }
        accFile.close();
    }

    std::ofstream expFile(expressageFile);
    if (expFile.is_open()) {
        expFile << expressage.size() << "\n";
        for (const auto& exp : expressage) {
            expFile << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " "
                    << exp.getAssignTime() << " " << (exp.getFlag() ? exp.getSignTime() : "NULL") << " "
                    << (exp.getFlag() ? 1 : 0) << " " << exp.getRemark() << "\n";
        }
        expFile.close();
    }
}

int LogisticSys::Login(std::string _id, std::string _pwd) {
    for (int i = 0; i < account.size(); ++i) {
        if (account[i].getId() == _id && account[i].getPassword() == _pwd) {
            return i;
        }
    }
    return -1;
}

AccountNode LogisticSys::queryInfo(int curAccount) {
    return account[curAccount];
}

bool LogisticSys::changePassword(int curAccount, std::string oldpwd, std::string newpwd) {
    if (account[curAccount].getPassword() == oldpwd) {
        account[curAccount].setPassword(newpwd);
        return true;
    }
    return false;
}

double LogisticSys::queryMoney(int curAccount) {
    return account[curAccount].getMoney();
}

double LogisticSys::addMoney(int curAccount, double money) {
    account[curAccount].setMoney(account[curAccount].getMoney() + money);
    return account[curAccount].getMoney();
}

bool LogisticSys::assignExpressage(int curAccount, std::string receiverId, std::string remark, std::string time) {
    int receiverIdx = -1;
    for (int i = 0; i < account.size(); ++i) {
        if (account[i].getId() == receiverId) {
            receiverIdx = i;
            break;
        }
    }

    if (receiverIdx == -1 || receiverIdx == rootIndex) {
        receiverIdx = rootIndex;
    } else if (account[receiverIdx].getMoney() < 0) { // Logic check based on PRD
        return false;
    }

    if (account[curAccount].getMoney() < 15.0) return false;

    account[curAccount].setMoney(account[curAccount].getMoney() - 15.0);
    if (rootIndex != -1) {
        account[rootIndex].setMoney(account[rootIndex].getMoney() + 15.0);
    }

    std::string newId = "KD";
    int num = expressage.size() + 1;
    std::stringstream ss;
    ss << std::setw(8) << std::setfill('0') << num;
    newId += ss.str();

    expressage.emplace_back(newId, account[curAccount].getId(), receiverId, time, "NULL", remark, false);
    expressageNum++;
    return true;
}

bool LogisticSys::signExpressage(int curAccount, std::string id, std::string time) {
    for (auto& exp : expressage) {
        if (exp.getId() == id && exp.getReceiveUser() == account[curAccount].getId()) {
            if (exp.Sign(time)) return true;
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int curAccount) {
    std::vector<ExpressageNode> result;
    authority userType = account[curAccount].getType();
    for (const auto& exp : expressage) {
        if (userType == authority::root || userType == authority::admin) {
            result.push_back(exp);
        } else {
            if (exp.getSendUser() == account[curAccount].getId() || exp.getReceiveUser() == account[curAccount].getId()) {
                result.push_back(exp);
            }
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int curAccount, std::string id) {
    for (const auto& exp : expressage) {
        if (exp.getId() == id) {
            if (exp.getSendUser() == account[curAccount].getId() || exp.getReceiveUser() == account[curAccount].getId()) {
                return exp;
            }
        }
    }
    return ExpressageNode(); // Return empty/invalid node if not found or unauthorized
}
