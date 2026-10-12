#include <iostream>
#include <string>
#include "logistics.h"

int main() {
    LogisticSys sys;
    sys.init("data/account.txt", "data/expressage.txt");

    std::string op;
    int curAccount = -1;

    while (true) {
        std::cout << "Enter operation (reg/login/exit): ";
        std::cin >> op;

        if (op == "reg") {
            std::string id, pwd, name, phone, address;
            double money = 0.0;
            std::cout << "Enter username, password, name, phone, address: ";
            std::cin >> id >> pwd >> name >> phone >> address;
            if (sys.Regist(id, pwd, name, phone, money, address)) {
                std::cout << "Succeed." << std::endl;
            } else {
                std::cout << "Failed." << std::endl;
            }
        } else if (op == "login") {
            std::string id, pwd;
            std::cout << "Enter username and password: ";
            std::cin >> id >> pwd;
            curAccount = sys.Login(id, pwd);
            if (curAccount != -1) {
                std::cout << "Welcome!" << std::endl;
                AccountNode info = sys.queryInfo(curAccount);
                std::cout << "AccountId: " << info.getId() << std::endl;
                std::cout << "UserName: " << info.getName() << std::endl;
                std::cout << "UserPhone: " << info.getPhone() << std::endl;
                std::cout << "Money: " << info.getMoney() << std::endl;
                std::cout << "Address: " << info.getAddress() << std::endl;
                std::cout << "UserType: ";
                if (info.getType() == authority::root) {
                    std::cout << "root" << std::endl;
                } else if (info.getType() == authority::admin) {
                    std::cout << "admin" << std::endl;
                } else {
                    std::cout << "normal user" << std::endl;
                }

                while (true) {
                    std::cout << "Enter operation (cpwd/exit/send/sign/qm/recharge/qall/qalls/qallr/qs/qr/qt/q): ";
                    std::cin >> op;

                    if (op == "cpwd") {
                        std::string opwd, pwd;
                        std::cout << "Enter old password and new password: ";
                        std::cin >> opwd >> pwd;
                        if (sys.changePassword(curAccount, opwd, pwd)) {
                            std::cout << "Succeed." << std::endl;
                        } else {
                            std::cout << "Failed." << std::endl;
                        }
                    } else if (op == "exit") {
                        std::cout << "Bye!" << std::endl;
                        break;
                    } else if (op == "send") {
                        std::string recipient, remark, time;
                        std::cout << "Enter recipient, remark, send time: ";
                        std::cin >> recipient >> remark >> time;
                        if (sys.assignExpressage(curAccount, recipient, remark, time)) {
                            std::cout << "Succeed." << std::endl;
                        } else {
                            std::cout << "Failed." << std::endl;
                        }
                    } else if (op == "sign") {
                        std::string expressageId, time;
                        std::cout << "Enter expressage id and sign time: ";
                        std::cin >> expressageId >> time;
                        if (sys.signExpressage(curAccount, expressageId, time)) {
                            std::cout << "Succeed." << std::endl;
                        } else {
                            std::cout << "Failed." << std::endl;
                        }
                    } else if (op == "qm") {
                        double money = sys.queryMoney(curAccount);
                        std::cout << "Rest money: " << money << std::endl;
                    } else if (op == "recharge") {
                        double amount;
                        std::cout << "Enter recharge amount: ";
                        std::cin >> amount;
                        if (amount >= 0) {
                            sys.addMoney(curAccount, amount);
                            double money = sys.queryMoney(curAccount);
                            std::cout << "Rest money: " << money << std::endl;
                        } else {
                            std::cout << "Failed." << std::endl;
                        }
                    } else if (op == "qall") {
                        std::vector<ExpressageNode> expressages = sys.queryAllExpressage(curAccount);
                        for (const auto& expressage : expressages) {
                            std::cout << expressage << std::endl;
                        }
                    } else if (op == "qalls") {
                        // Implement queryAllSentExpressage if needed
                    } else if (op == "qallr") {
                        // Implement queryAllReceivedExpressage if needed
                    } else if (op == "qs") {
                        std::string sender;
                        std::cout << "Enter sender username: ";
                        std::cin >> sender;
                        // Implement querySentExpressage if needed
                    } else if (op == "qr") {
                        std::string receiver;
                        std::cout << "Enter receiver username: ";
                        std::cin >> receiver;
                        // Implement queryReceivedExpressage if needed
                    } else if (op == "qt") {
                        std::string time;
                        std::cout << "Enter send time: ";
                        std::cin >> time;
                        // Implement queryExpressageByTime if needed
                    } else if (op == "q") {
                        std::string expressageId;
                        std::cout << "Enter expressage id: ";
                        std::cin >> expressageId;
                        ExpressageNode expressage = sys.queryExpressage(curAccount, expressageId);
                        if (expressage.getId().empty()) {
                            std::cout << "Failed." << std::endl;
                        } else {
                            std::cout << expressage << std::endl;
                        }
                    } else {
                        std::cout << "Wrong operation name." << std::endl;
                    }
                }
            } else {
                std::cout << "Wrong account id or/and password." << std::endl;
            }
        } else if (op == "exit") {
            std::cout << "Bye!" << std::endl;
            break;
        } else {
            std::cout << "Wrong operation name." << std::endl;
        }
    }

    sys.save("data/account.txt", "data/expressage.txt");
    return 0;
}
