#include "logistics.h"
#include "account.h"
#include "expressage.h"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include <vector>

using namespace std;

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

void LogisticSys::init(string accFile, string expFile) {
    account.clear();
    expressage.clear();
    
    ifstream accIn(accFile);
    if (accIn.is_open()) {
        int n;
        if (!(accIn >> n)) n = 0;
        for (int i = 0; i < n; ++i) {
            string id, pwd, name, phone, addr;
            double money;
            int type;
            accIn >> id >> pwd >> name >> phone >> money >> addr >> type;
            account.emplace_back(id, pwd, name, phone, money, addr, static_cast<authority>(type));
        }
        accIn.close();
    }
    
    rootIndex = -1;
    for(int i=0; i<(int)account.size(); ++i) {
        if(static_cast<int>(account[i].getType()) == 0) {
            rootIndex = i;
            break;
        }
    }

    ifstream expIn(expFile);
    if (expIn.is_open()) {
        int m;
        if (!(expIn >> m)) m = 0;
        for (int i = 0; i < m; ++i) {
            string id, sUser, rUser, sTime, dTime, remark;
            int status;
            expIn >> id >> sUser >> rUser >> sTime >> dTime >> status >> remark;
            expressage.emplace_back(id, sUser, rUser, sTime, dTime, remark, (status == 1));
        }
        expIn.close();
    }
}

void LogisticSys::save(string accFile, string expFile) {
    ofstream accOut(accFile);
    if (accOut.is_open()) {
        accOut << account.size() << endl;
        for (const auto& acc : account) {
            accOut << acc.getId() << " " << acc.getPassword() << " " << acc.getName() << " "
                   << acc.getPhone() << " " << acc.getMoney() << " " << acc.getAddress() << " "
                   << static_cast<int>(acc.getType()) << endl;
        }
        accOut.close();
    }

    ofstream expOut(expFile);
    if (expOut.is_open()) {
        expOut << expressage.size() << endl;
        for (const auto& exp : expressage) {
            expOut << exp.getId() << " " << exp.getSendUser() << " " << exp.getReceiveUser() << " "
                   << exp.getAssignTime() << " " << exp.getSignTime() << " " 
                   << (exp.getFlag() ? 1 : 0) << " " << exp.getRemark() << endl;
        }
        expOut.close();
    }
}

bool LogisticSys::Regist(string id, string pwd, string name, string phone, double money, string addr) {
    for (const auto& acc : account) {
        if (acc.getId() == id) return false;
    }
    account.emplace_back(id, pwd, name, phone, money, addr, authority::user);
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
    if (idx >= 0 && idx < (int)account.size()) return account[idx];
    return AccountNode();
}

bool LogisticSys::changePassword(int idx, string opwd, string npwd) {
    if (idx >= 0 && idx < (int)account.size() && account[idx].getPassword() == opwd) {
        account[idx].setPassword(npwd);
        return true;
    }
    return false;
}

double LogisticSys::queryMoney(int idx) {
    if (idx >= 0 && idx < (int)account.size()) return account[idx].getMoney();
    return 0.0;
}

double LogisticSys::addMoney(int idx, double amount) {
    if (idx >= 0 && idx < (int)account.size()) {
        account[idx].setMoney(account[idx].getMoney() + amount);
        return account[idx].getMoney();
    }
    return 0.0;
}

bool LogisticSys::assignExpressage(int senderIdx, string receiverId, string remark, string time) {
    if (senderIdx < 0 || senderIdx >= (int)account.size()) return false;
    if (account[senderIdx].getMoney() < 15.0) return false;

    int targetIdx = -1;
    for (int i = 0; i < (int)account.size(); ++i) {
        if (account[i].getId() == receiverId) {
            targetIdx = i;
            break;
        }
    }

    if (targetIdx == -1 || targetIdx == rootIndex) {
        targetIdx = rootIndex;
    }

    if (targetIdx == -1) return false;

    account[senderIdx].setMoney(account[senderIdx].getMoney() - 15.0);
    account[targetIdx].setMoney(account[targetIdx].getMoney() + 15.0);

    static int idCounter = 1;
    int maxId = 0;
    for(const auto& exp : expressage) {
        if(exp.getId().size() >= 10) {
            try {
                int val = stoi(exp.getId().substr(2));
                if(val > maxId) maxId = val;
            } catch(...) {}
        }
    }
    if (idCounter <= maxId) idCounter = maxId + 1;

    stringstream ss;
    ss << "KD" << setfill('0') << setw(8) << idCounter++;
    string newId = ss.str();

    expressage.emplace_back(newId, account[senderIdx].getId(), receiverId, time, "NULL", remark, false);
    return true;
}

bool LogisticSys::signExpressage(int userIdx, string expId, string time) {
    if (userIdx < 0 || userIdx >= (int)account.size()) return false;
    for (auto& exp : expressage) {
        if (exp.getId() == expId && exp.getReceiveUser() == account[userIdx].getId()) {
            exp.Sign(time);
            return true;
        }
    }
    return false;
}

vector<ExpressageNode> LogisticSys::queryAllExpressage(int userIdx) {
    vector<ExpressageNode> res;
    if (userIdx < 0 || userIdx >= (int)account.size()) return res;
    
    string uid = account[userIdx].getId();
    authority utype = account[userIdx].getType();

    for (const auto& exp : expressage) {
        if (static_cast<int>(utype) == 0 || static_cast<int>(utype) == 1) {
            res.push_back(exp);
        } else {
            if (exp.getSendUser() == uid || exp.getReceiveUser() == uid) {
                res.push_back(exp);
            }
        }
    }
    return res;
}

vector<ExpressageNode> LogisticSys::queryAlls(int userIdx) {
    vector<ExpressageNode> res;
    if (userIdx < 0 || userIdx >= (int)account.size()) return res;
    string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getSendUser() == uid) res.push_back(exp);
    }
    return res;
}

vector<ExpressageNode> LogisticSys::queryAllr(int userIdx) {
    vector<ExpressageNode> res;
    if (userIdx < 0 || userIdx >= (int)account.size()) return res;
    string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getReceiveUser() == uid) res.push_back(exp);
    }
    return res;
}

vector<ExpressageNode> LogisticSys::qs(int userIdx, string x) {
    vector<ExpressageNode> res;
    if (userIdx < 0 || userIdx >= (int)account.size()) return res;
    string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getSendUser() == x && (exp.getSendUser() == uid || exp.getReceiveUser() == uid)) {
            res.push_back(exp);
        }
    }
    return res;
}

vector<ExpressageNode> LogisticSys::qr(int userIdx, string x) {
    vector<ExpressageNode> res;
    if (userIdx < 0 || userIdx >= (int)account.size()) return res;
    string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getReceiveUser() == x && (exp.getSendUser() == uid || exp.getReceiveUser() == uid)) {
            res.push_back(exp);
        }
    }
    return res;
}

vector<ExpressageNode> LogisticSys::qt(int userIdx, string t) {
    vector<ExpressageNode> res;
    if (userIdx < 0 || userIdx >= (int)account.size()) return res;
    string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getAssignTime() == t && (exp.getSendUser() == uid || exp.getReceiveUser() == uid)) {
            res.push_back(exp);
        }
    }
    return res;
}

ExpressageNode LogisticSys::queryExpressage(int userIdx, string expId) {
    if (userIdx < 0 || userIdx >= (int)account.size()) return ExpressageNode();
    string uid = account[userIdx].getId();
    for (const auto& exp : expressage) {
        if (exp.getId() == expId && (exp.getSendUser() == uid || exp.getReceiveUser() == uid)) {
            return exp;
        }
    }
    return ExpressageNode(); 
}
