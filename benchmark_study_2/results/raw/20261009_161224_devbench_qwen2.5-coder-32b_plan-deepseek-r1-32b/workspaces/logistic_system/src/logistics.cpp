#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iomanip>

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

void LogisticSys::init(const std::string& accountFilePath, const std::string& expressageFilePath) {
    std::ifstream accountFile(accountFilePath);
    std::ifstream expressageFile(expressageFilePath);

    if (accountFile.is_open()) {
        accountFile >> accountNum;
        account.resize(accountNum);
        for (int i = 0; i < accountNum; ++i) {
            std::string id, password, name, phone, address;
            double money;
            int type;
            accountFile >> id >> password >> name >> phone >> money >> address >> type;
            account[i] = AccountNode(id, password, name, phone, money, address, static_cast<authority>(type));
            if (account[i].getType() == authority::root) {
                rootIndex = i;
            }
        }
        accountFile.close();
    }

    if (expressageFile.is_open()) {
        expressageFile >> expressageNum;
        expressage.resize(expressageNum);
        for (int i = 0; i < expressageNum; ++i) {
            std::string id, sendUser, receiveUser, assignTime, signTime, remark;
            bool flag;
            expressageFile >> id >> sendUser >> receiveUser >> assignTime >> signTime >> flag >> remark;
            expressage[i] = ExpressageNode(id, sendUser, receiveUser, assignTime, signTime, remark, flag);
        }
        expressageFile.close();
    }
}

void LogisticSys::save(const std::string& accountFilePath, const std::string& expressageFilePath) {
    std::ofstream accountFile(accountFilePath);
    std::ofstream expressageFile(expressageFilePath);

    if (accountFile.is_open()) {
        accountFile << accountNum << "\n";
        for (const auto& acc : account) {
            accountFile << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " " << acc.getPhone() << " " << std::fixed << std::setprecision(2) << acc.getMoney() << " " << acc.getAddress() << " ";
            if (acc.getType() == authority::root) {
                accountFile << "0";
            } else if (acc.getType() == authority::admin) {
                accountFile << "1";
            } else {
                accountFile << "2";
            }
            accountFile << "\n";
        }
        accountFile.close();
    }

    if (expressageFile.is_open()) {
        expressageFile << expressageNum << "\n";
        for (const auto& exp : expressage) {
            expressageFile << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " " << exp.getAssignTime() << " " << exp.getSignTime() << " " << exp.getFlag() << " " << exp.getRemark() << "\n";
        }
        expressageFile.close();
    }
}

int LogisticSys::Login(const std::string& id, const std::string& pwd) {
    for (int i = 0; i < accountNum; ++i) {
        if (account[i].getId() == id && account[i].getPassword() == pwd) {
            return i;
        }
    }
    return -1;
}

bool LogisticSys::Regist(const std::string& id, const std::string& pwd, const std::string& name, const std::string& phone, double money, const std::string& address) {
    for (const auto& acc : account) {
        if (acc.getId() == id) {
            return false;
        }
    }
    account.push_back(AccountNode(id, pwd, name, phone, money, address, authority::normal_user));
    accountNum++;
    return true;
}

bool LogisticSys::changePassword(int accountIndex, const std::string& oldPwd, const std::string& newPwd) {
    if (account[accountIndex].getPassword() == oldPwd) {
        account[accountIndex] = AccountNode(account[accountIndex].getId(), newPwd, account[accountIndex].getName(), account[accountIndex].getPhone(), account[accountIndex].getMoney(), account[accountIndex].getAddress(), account[accountIndex].getType());
        return true;
    }
    return false;
}

AccountNode LogisticSys::queryInfo(int accountIndex) {
    return account[accountIndex];
}

double LogisticSys::queryMoney(int accountIndex) {
    return account[accountIndex].getMoney();
}

double LogisticSys::addMoney(int accountIndex, double amount) {
    account[accountIndex] = AccountNode(account[accountIndex].getId(), account[accountIndex].getPassword(), account[accountIndex].getName(), account[accountIndex].getPhone(), account[accountIndex].getMoney() + amount, account[accountIndex].getAddress(), account[accountIndex].getType());
    return account[accountIndex].getMoney();
}

bool LogisticSys::assignExpressage(int accountIndex, const std::string& receiverId, const std::string& remark, const std::string& time) {
    if (account[accountIndex].getMoney() < 15) {
        return false;
    }
    for (const auto& acc : account) {
        if (acc.getId() == receiverId && acc.getId() != account[accountIndex].getId() && acc.getMoney() >= 0) {
            account[accountIndex] = AccountNode(account[accountIndex].getId(), account[accountIndex].getPassword(), account[accountIndex].getName(), account[accountIndex].getPhone(), account[accountIndex].getMoney() - 15, account[accountIndex].getAddress(), account[accountIndex].getType());
            account[rootIndex] = AccountNode(account[rootIndex].getId(), account[rootIndex].getPassword(), account[rootIndex].getName(), account[rootIndex].getPhone(), account[rootIndex].getMoney() + 15, account[rootIndex].getAddress(), account[rootIndex].getType());
            expressage.push_back(ExpressageNode("KD" + std::to_string(expressageNum + 1), account[accountIndex].getId(), receiverId, time, "NULL", remark, false));
            expressageNum++;
            return true;
        }
    }
    return false;
}

bool LogisticSys::signExpressage(int accountIndex, const std::string& expressageId, const std::string& time) {
    for (auto& exp : expressage) {
        if (exp.getId() == expressageId && exp.getReceiveUser() == account[accountIndex].getId() && !exp.getFlag()) {
            exp = ExpressageNode(exp.getId(), exp.getSendUser(), exp.getReceiveUser(), exp.getAssignTime(), time, exp.getRemark(), true);
            return true;
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int accountIndex) {
    std::vector<ExpressageNode> result;
    for (const auto& exp : expressage) {
        if (account[accountIndex].getType() == authority::root || account[accountIndex].getType() == authority::admin || exp.getSendUser() == account[accountIndex].getId() || exp.getReceiveUser() == account[accountIndex].getId()) {
            result.push_back(exp);
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int accountIndex, const std::string& expressageId) {
    for (const auto& exp : expressage) {
        if (exp.getId() == expressageId && (account[accountIndex].getType() == authority::root || account[accountIndex].getType() == authority::admin || exp.getSendUser() == account[accountIndex].getId() || exp.getReceiveUser() == account[accountIndex].getId())) {
            return exp;
        }
    }
    return ExpressageNode();
}
