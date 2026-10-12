#include <iostream>
#include <iomanip>
#include <string>
#include "logistics.h"

using namespace std;

int main() {
    LogisticSys sys;
    sys.init("data/account.txt", "data/expressage.txt");

    string op;
    bool loggedIn = false;
    int curAccount = -1;

    while (true) {
        if (!loggedIn) {
            cin >> op;
            if (op == "reg") {
                string id, pwd, name, phone, address;
                cin >> id >> pwd >> name >> phone >> address;
                if (sys.Regist(id, pwd, name, phone, 0, address)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "login") {
                string id, pwd;
                cin >> id >> pwd;
                curAccount = sys.Login(id, pwd);
                if (curAccount != -1) {
                    cout << "Welcome!" << endl;
                    loggedIn = true;
                    AccountNode accountInfo = sys.queryInfo(curAccount);
                    cout << "AccountId: " << accountInfo.getId() << endl;
                    cout << "UserName: " << accountInfo.namePublic() << endl;
                    cout << "UserPhone: " << accountInfo.phonePublic() << endl;
                    cout << "Money: " << fixed << setprecision(2) << accountInfo.getMoney() << endl;
                    cout << "Address: " << accountInfo.addressPublic() << endl;
                    string userType;
                    switch (accountInfo.getType()) {
                        case authority::root:
                            userType = "root";
                            break;
                        case authority::admin:
                            userType = "admin";
                            break;
                        case authority::user:
                            userType = "normal user";
                            break;
                    }
                    cout << "UserType: " << userType << endl;
                } else {
                    cout << "Wrong account id or/and password." << endl;
                }
            } else if (op == "exit") {
                cout << "Bye!" << endl;
                break;
            } else {
                cout << "Wrong operation name." << endl;
            }
        } else {
            cin >> op;
            if (op == "cpwd") {
                string oldPwd, newPwd;
                cin >> oldPwd >> newPwd;
                if (sys.changePassword(curAccount, oldPwd, newPwd)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "exit") {
                cout << "Bye!" << endl;
                break;
            } else if (op == "send") {
                string recipient, remark, sendTime;
                cin >> recipient >> remark >> sendTime;
                if (sys.assignExpressage(curAccount, recipient, remark, sendTime)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "sign") {
                string expressageId, signTime;
                cin >> expressageId >> signTime;
                if (sys.signExpressage(curAccount, expressageId, signTime)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "qm") {
                double money = sys.queryMoney(curAccount);
                cout << "Rest money: " << fixed << setprecision(2) << money << endl;
            } else if (op == "recharge") {
                double amount;
                cin >> amount;
                if (amount >= 0) {
                    double newMoney = sys.addMoney(curAccount, amount);
                    cout << "Rest money: " << fixed << setprecision(2) << newMoney << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "qall") {
                vector<ExpressageNode> expressages = sys.queryAllExpressage(curAccount);
                for (const auto& expressage : expressages) {
                    cout << "Expressage id: " << expressage.id << endl;
                    cout << "Sender: " << expressage.sendUser << endl;
                    cout << "Recipient: " << expressage.receiveUser << endl;
                    cout << "Send Time: " << expressage.assignTime << endl;
                    cout << "Status: " << (expressage.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.signTime.empty() ? "NULL" : expressage.signTime) << endl;
                    cout << "Remark: " << expressage.remark << endl;
                }
            } else if (op == "qalls") {
                // Implement if needed
            } else if (op == "qallr") {
                // Implement if needed
            } else if (op == "qs") {
                // Implement if needed
            } else if (op == "qr") {
                // Implement if needed
            } else if (op == "qt") {
                // Implement if needed
            } else if (op == "q") {
                string expressageId;
                cin >> expressageId;
                ExpressageNode expressage = sys.queryExpressage(curAccount, expressageId);
                if (!expressage.id.empty()) {
                    cout << "Expressage id: " << expressage.id << endl;
                    cout << "Sender: " << expressage.sendUser << endl;
                    cout << "Recipient: " << expressage.receiveUser << endl;
                    cout << "Send Time: " << expressage.assignTime << endl;
                    cout << "Status: " << (expressage.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.signTime.empty() ? "NULL" : expressage.signTime) << endl;
                    cout << "Remark: " << expressage.remark << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else {
                cout << "Wrong operation name." << endl;
            }
        }
    }

    sys.save("data/account.txt", "data/expressage.txt");
    return 0;
}
