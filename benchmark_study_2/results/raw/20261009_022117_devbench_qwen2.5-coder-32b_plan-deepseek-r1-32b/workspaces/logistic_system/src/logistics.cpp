#include "logistics.h"
#include <fstream>
#include <sstream>
#include <iomanip>

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

bool LogisticSys::Regist(std::string id, std::string pwd, std::string name, std::string phone, double money, std::string address) {
    for (const auto& acc : account) {
        if (acc.getId() == id) {
            return false;
        }
    }
    AccountNode newAccount(id, pwd, name, phone, money, address, authority::normal_user);
    account.push_back(newAccount);
    accountNum++;
    return true;
}

void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    std::ifstream accountStream(accountFile);
    std::ifstream expressageStream(expressageFile);

    if (!accountStream.is_open() || !expressageStream.is_open()) {
        throw std::runtime_error("Failed to open files for initialization.");
    }

    // Read account information
    int accountCount;
    accountStream >> accountCount;
    accountStream.ignore(); // Ignore newline character

    for (int i = 0; i < accountCount; ++i) {
        std::string id, password, name, phone, address;
        double money;
        int type;

        std::getline(accountStream, id, ' ');
        std::getline(accountStream, password, ' ');
        std::getline(accountStream, name, ' ');
        std::getline(accountStream, phone, ' ');
        accountStream >> money;
        accountStream.ignore(); // Ignore space
        std::getline(accountStream, address, ' ');
        accountStream >> type;
        accountStream.ignore(); // Ignore newline character

        AccountNode newAccount(id, password, name, phone, money, address, static_cast<authority>(type));
        account.push_back(newAccount);

        if (type == 0) {
            rootIndex = i;
        }
    }

    // Read expressage information
    int expressageCount;
    expressageStream >> expressageCount;
    expressageStream.ignore(); // Ignore newline character

    for (int i = 0; i < expressageCount; ++i) {
        std::string id, sendUser, receiveUser, assignTime, signTime, remark;
        bool flag;

        std::getline(expressageStream, id, ' ');
        std::getline(expressageStream, sendUser, ' ');
        std::getline(expressageStream, receiveUser, ' ');
        std::getline(expressageStream, assignTime, ' ');
        std::getline(expressageStream, signTime, ' ');
        expressageStream >> flag;
        expressageStream.ignore(); // Ignore space
        std::getline(expressageStream, remark, '\n');

        ExpressageNode newExpressage(id, sendUser, receiveUser, assignTime, signTime, remark, flag);
        expressage.push_back(newExpressage);
    }

    accountNum = accountCount;
    expressageNum = expressageCount;
}

void LogisticSys::save(std::string accountFile, std::string expressageFile) {
    std::ofstream accountStream(accountFile);
    std::ofstream expressageStream(expressageFile);

    if (!accountStream.is_open() || !expressageStream.is_open()) {
        throw std::runtime_error("Failed to open files for saving.");
    }

    // Save account information
    accountStream << accountNum << std::endl;
    for (const auto& acc : account) {
        accountStream << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " " << acc.getPhone() << " "
                      << acc.getMoney() << " " << acc.getAddress() << " " << static_cast<int>(acc.getType()) << std::endl;
    }

    // Save expressage information
    expressageStream << expressageNum << std::endl;
    for (const auto& exp : expressage) {
        expressageStream << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " "
                         << exp.getAssignTime() << " " << exp.getSignTime() << " " << exp.getFlag() << " " << exp.getRemark() << std::endl;
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
    if (index >= 0 && index < accountNum) {
        return account[index];
    }
    throw std::out_of_range("Invalid account index");
}

bool LogisticSys::changePassword(int index, std::string oldPwd, std::string newPwd) {
    if (index >= 0 && index < accountNum && account[index].getPassword() == oldPwd) {
        account[index].setPassword(newPwd);
        return true;
    }
    return false;
}

double LogisticSys::queryMoney(int index) {
    if (index >= 0 && index < accountNum) {
        return account[index].getMoney();
    }
    throw std::out_of_range("Invalid account index");
}

double LogisticSys::addMoney(int index, double amount) {
    if (index >= 0 && index < accountNum) {
        account[index].setMoney(account[index].getMoney() + amount);
        return account[index].getMoney();
    }
    throw std::out_of_range("Invalid account index");
}

bool LogisticSys::assignExpressage(int index, std::string receiverId, std::string remark, std::string time) {
    if (index >= 0 && index < accountNum) {
        for (const auto& acc : account) {
            if (acc.getId() == receiverId) {
                if (acc.getId() == account[rootIndex].getId() || acc.getMoney() < 15.0) {
                    return false;
                }
                std::ostringstream oss;
                oss << "KD" << std::setw(8) << std::setfill('0') << expressageNum + 1;
                std::string newId = oss.str();
                ExpressageNode newExpressage(newId, account[index].getId(), receiverId, time, "NULL", remark, false);
                expressage.push_back(newExpressage);
                expressageNum++;
                account[index].setMoney(account[index].getMoney() - 15.0);
                account[rootIndex].setMoney(account[rootIndex].getMoney() + 15.0);
                return true;
            }
        }
    }
    return false;
}

bool LogisticSys::signExpressage(int index, std::string expressageId, std::string time) {
    for (auto& exp : expressage) {
        if (exp.getId() == expressageId && exp.getReceiveUser() == account[index].getId() && !exp.getFlag()) {
            exp.Sign(time);
            return true;
        }
    }
    return false;
}

std::vector<ExpressageNode> LogisticSys::queryAllExpressage(int index) {
    std::vector<ExpressageNode> result;
    for (const auto& exp : expressage) {
        if (account[index].getType() == authority::root || account[index].getType() == authority::admin ||
            exp.getSendUser() == account[index].getId() || exp.getReceiveUser() == account[index].getId()) {
            result.push_back(exp);
        }
    }
    return result;
}

ExpressageNode LogisticSys::queryExpressage(int index, std::string expressageId) {
    for (const auto& exp : expressage) {
        if (exp.getId() == expressageId) {
            return exp;
        }
    }
    throw std::runtime_error("Expressage not found");
}
