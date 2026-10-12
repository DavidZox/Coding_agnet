#include "logistics.h"
#include <iostream>
#include <string>
#include <vector>
#include <iomanip>

int main() {
    LogisticSys sys;
    sys.init("data/account.txt", "data/expressage.txt");

    std::string op;
    bool loggedIn = false;
    int currentAccountIdx = -1;

    while (true) {
        if (!loggedIn) {
            if (!(std::cin >> op)) break;
            if (op == "reg") {
                std::string id, pwd, name, phone, address;
                std::cin >> id >> pwd >> name >> phone >> address;
                if (sys.Regist(id, pwd, name, phone, 0.0, address)) {
                    std::cout << "Succeed." << std::endl;
                } else {
                    std::cout << "Failed." << std::endl;
                }
            } else if (op == "login") {
                std::string id, pwd;
                std::cin >> id >> pwd;
                int idx = sys.Login(id, pwd);
                if (idx != -1) {
                    loggedIn = true;
                    currentAccountIdx = idx;
                    std::cout << "Welcome!" << std::endl;
                } else {
                    std::cout << "Wrong account id or/and password." << std::endl;
                }
            } else if (op == "exit") {
                std::cout << "Bye!" << std::endl;
                break;
            } else {
                std::cout << "Wrong operation name." << std::endl;
            }
        } else {
            AccountNode info = sys.queryInfo(currentAccountIdx);
            std::string typeStr;
            if (info.getType() == authority::root) typeStr = "root";
            else if (info.getType() == authority::admin) typeStr = "admin";
            else typeStr = "normal user";

            std::cout << "AccountId: " << info.getId() << "\n";
            std::cout << "UserName: " << info.getName() << "\n";
            std::cout << "UserPhone: " << info.getPhone() << "\n";
            std::cout << "Money: " << (int)info.getMoney() << "\n"; // PRD example shows integer-like display for money in user info
            // Note: PRD says "Money: 100", but qm says "Rest money: money" with 2 decimal places. 
            // Following the specific "After Successful Login" block format:
            std::cout << "Address: " << info.getAddress() << "\n";
            std::cout << "UserType: " << typeStr << std::endl;

            if (!(std::cin >> op)) break;

            if (op == "cpwd") {
                std::string oldpwd, newpwd;
                std::cin >> oldpwd >> newpwd;
                if (sys.changePassword(currentAccountIdx, oldpwd, newpwd)) {
                    std::cout << "Succeed." << std::endl;
                } else {
                    std::cout << "Failed." << std::endl;
                }
            } else if (op == "exit") {
                std::cout << "Bye!" << std::endl;
                break;
            } else if (op == "send") {
                std::string receiverId, remark, time;
                std::cin >> receiverId >> remark >> time;
                if (sys.assignExpressage(currentAccountIdx, receiverId, remark, time)) {
                    std::cout << "Succeed." << std::endl;
                } else {
                    std::cout << "Failed." << std::endl;
                }
            } else if (op == "sign") {
                std::string id, time;
                std::cin >> id >> time;
                if (sys.signExpressage(currentAccountIdx, id, time)) {
                    std::cout << "Succeed." << std::endl;
                } else {
                    std::cout << "Failed." << std::endl;
                }
            } else if (op == "qm") {
                double money = sys.queryMoney(currentAccountIdx);
                std::cout << "Rest money: " << std::fixed << std::setprecision(2) << money << std::endl;
            } else if (op == "recharge") {
                double amount;
                std::cin >> amount;
                if (amount < 0) {
                    std::cout << "Failed." << std::endl;
                } else {
                    double newMoney = sys.addMoney(currentAccountIdx, amount);
                    std::cout << "Rest money: " << std::fixed << std::setprecision(2) << newMoney << std::endl;
                }
            } else if (op == "qall") {
                std::vector<ExpressageNode> list = sys.queryAllExpressage(currentAccountIdx);
                for (auto& e : list) {
                    std::cout << e << std::endl;
                }
            } else if (op == "qalls") {
                // PRD says qalls is "all packages sent by current user"
                // Implementation in logistics.cpp queryAllExpressage handles root/admin/normal logic.
                // To strictly follow qalls/qallr/qs/qr/qt/q, we use the specific logic.
                // Since queryAllExpressage is the only general query provided in header:
                // We'll assume qall covers the general requirement or implement specific filters if needed.
                // However, the header only provides queryAllExpressage(int).
                // Let's use queryAllExpressage and filter manually if the header allowed, 
                // but we must stick to the provided header.
                // For the sake of this task, we will use the provided queryAllExpressage.
                std::vector<ExpressageNode> list = sys.queryAllExpressage(currentAccountIdx);
                for (auto& e : list) {
                    if (e.getSendUser() == info.getId()) std::cout << e << std::endl;
                }
            } else if (op == "qallr") {
                std::vector<ExpressageNode> list = sys.queryAllExpressage(currentAccountIdx);
                for (auto& e : list) {
                    if (e.getReceiveUser() == info.getId()) std::cout << e << std::endl;
                }
            } else if (op == "qs") {
                std::string x;
                std::cin >> x;
                std::vector<ExpressageNode> list = sys.queryAllExpressage(currentAccountIdx);
                for (auto& e : list) {
                    if (e.getSendUser() == x) std::cout << e << std::endl;
                }
            } else if (op == "qr") {
                std::string x;
                std::cin >> x;
                std::vector<ExpressageNode> list = sys.queryAllExpressage(currentAccountIdx);
                for (auto& e : list) {
                    if (e.getReceiveUser() == x) std::cout << e << std::endl;
                }
            } else if (op == "qt") {
                std::string t;
                std::cin >> t;
                std::vector<ExpressageNode> list = sys.queryAllExpressage(currentAccountIdx);
                for (auto& e : list) {
                    if (e.getAssignTime() == t) std::cout << e << std::endl;
                }
            } else if (op == "q") {
                std::string id;
                std::cin >> id;
                ExpressageNode e = sys.queryExpressage(currentAccountIdx, id);
                if (e.getId() == "") std::cout << "Failed." << std::endl;
                else std::cout << e << std::endl;
            } else {
                std::cout << "Wrong operation name." << std::endl;
            }
        }
    }

    sys.save("data/account.txt", "data/expressage.txt");
    return 0;
}
