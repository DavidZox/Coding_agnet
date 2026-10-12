#include <iostream>
#include <string>
#include "logistics.h"

int main() {
    LogisticSys sys;
    sys.init("data/account.txt", "data/expressage.txt");

    std::string op;
    bool loginFlag = false;
    int curAccount = -1;

    while (!loginFlag) {
        std::cin >> op;
        if (op == "reg") {
            std::string id, pwd, nm, ph, ad;
            double m;
            std::cin >> id >> pwd >> nm >> ph >> m >> ad;
            if (sys.Regist(id, pwd, nm, ph, m, ad)) {
                std::cout << "Succeed." << std::endl;
            } else {
                std::cout << "Failed." << std::endl;
            }
        } else if (op == "login") {
            std::string id, pwd;
            std::cin >> id >> pwd;
            curAccount = sys.Login(id, pwd);
            if (curAccount != -1) {
                std::cout << "Welcome!" << std::endl;
                loginFlag = true;
            } else {
                std::cout << "Wrong account id or/and password." << std::endl;
            }
        } else if (op == "exit") {
            std::cout << "Bye!" << std::endl;
            return 0;
        } else {
            std::cout << "Wrong operation name." << std::endl;
        }
    }

    std::cout << sys.queryInfo(curAccount);

    while (loginFlag) {
        std::cin >> op;
        if (op == "cpwd") {
            std::string oldpwd, newpwd;
            std::cin >> oldpwd >> newpwd;
            if (sys.changePassword(curAccount, oldpwd, newpwd)) {
                std::cout << "Succeed." << std::endl;
            } else {
                std::cout << "Failed." << std::endl;
            }
        } else if (op == "exit") {
            std::cout << "Bye!" << std::endl;
            sys.save("data/account.txt", "data/expressage.txt");
            return 0;
        } else if (op == "send") {
            std::string receiverId, remark, time;
            std::cin >> receiverId >> remark >> time;
            if (sys.assignExpressage(curAccount, receiverId, remark, time)) {
                std::cout << "Succeed." << std::endl;
            } else {
                std::cout << "Failed." << std::endl;
            }
        } else if (op == "sign") {
            std::string id, time;
            std::cin >> id >> time;
            if (sys.signExpressage(curAccount, id, time)) {
                std::cout << "Succeed." << std::endl;
            } else {
                std::cout << "Failed." << std::endl;
            }
        } else if (op == "qm") {
            std::cout << "Rest money: " << std::fixed << std::setprecision(2) << sys.queryMoney(curAccount) << std::endl;
        } else if (op == "recharge") {
            double money;
            std::cin >> money;
            if (money >= 0) {
                std::cout << "Rest money: " << std::fixed << std::setprecision(2) << sys.addMoney(curAccount, money) << std::endl;
            } else {
                std::cout << "Failed." << std::endl;
            }
        } else if (op == "qall") {
            for (const auto& exp : sys.queryAllExpressage(curAccount)) {
                std::cout << exp;
            }
        } else if (op == "qalls") {
            for (const auto& exp : sys.queryAllExpressage(curAccount)) {
                if (exp.sendUser == sys.queryInfo(curAccount).id) {
                    std::cout << exp;
                }
            }
        } else if (op == "qallr") {
            for (const auto& exp : sys.queryAllExpressage(curAccount)) {
                if (exp.receiveUser == sys.queryInfo(curAccount).id) {
                    std::cout << exp;
                }
            }
        } else if (op == "qs") {
            std::string x;
            std::cin >> x;
            for (const auto& exp : sys.queryAllExpressage(curAccount)) {
                if (exp.sendUser == x) {
                    std::cout << exp;
                }
            }
        } else if (op == "qr") {
            std::string x;
            std::cin >> x;
            for (const auto& exp : sys.queryAllExpressage(curAccount)) {
                if (exp.receiveUser == x) {
                    std::cout << exp;
                }
            }
        } else if (op == "qt") {
            std::string t;
            std::cin >> t;
            for (const auto& exp : sys.queryAllExpressage(curAccount)) {
                if (exp.assignTime == t) {
                    std::cout << exp;
                }
            }
        } else if (op == "q") {
            std::string id;
            std::cin >> id;
            ExpressageNode exp = sys.queryExpressage(curAccount, id);
            if (exp.id.empty()) {
                std::cout << "Failed." << std::endl;
            } else {
                std::cout << exp;
            }
        } else {
            std::cout << "Wrong operation name." << std::endl;
        }
    }

    return 0;
}
