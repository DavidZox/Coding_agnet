#include <iostream>
#include <string>
#include <iomanip>
#include "logistics.h"

using namespace std;

int main() {
    LogisticSys sys;
    sys.init("data/account.txt", "data/expressage.txt");

    string op;
    bool loggedIn = false;
    int curAccount = -1;

    while (!loggedIn) {
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
                loggedIn = true;
                cout << "Welcome!" << endl;
                AccountNode info = sys.queryInfo(curAccount);
                cout << "AccountId: " << info.getId() << endl;
                cout << "UserName: " << info.getName() << endl;
                cout << "UserPhone: " << info.getPhone() << endl;
                cout << "Money: " << fixed << setprecision(2) << info.getMoney() << endl;
                cout << "Address: " << info.getAddress() << endl;
                cout << "UserType: ";
                if (info.getType() == authority::root) {
                    cout << "root" << endl;
                } else if (info.getType() == authority::admin) {
                    cout << "admin" << endl;
                } else {
                    cout << "normal user" << endl;
                }
            } else {
                cout << "Wrong account id or/and password." << endl;
            }
        } else if (op == "exit") {
            cout << "Bye!" << endl;
            return 0;
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    while (loggedIn) {
        cin >> op;
        if (op == "cpwd") {
            string opwd, pwd;
            cin >> opwd >> pwd;
            if (sys.changePassword(curAccount, opwd, pwd)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "exit") {
            cout << "Bye!" << endl;
            loggedIn = false;
        } else if (op == "send") {
            string receiverId, remark, time;
            cin >> receiverId >> remark >> time;
            if (sys.assignExpressage(curAccount, receiverId, remark, time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "sign") {
            string expressageId, time;
            cin >> expressageId >> time;
            if (sys.signExpressage(curAccount, expressageId, time)) {
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
                cout << "Expressage id: " << expressage.getId() << endl;
                cout << "Sender: " << expressage.getSendUser() << endl;
                cout << "Recipient: " << expressage.getReceiveUser() << endl;
                cout << "Send Time: " << expressage.getAssignTime() << endl;
                cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                cout << "Remark: " << expressage.getRemark() << endl;
            }
        } else if (op == "qalls") {
            vector<ExpressageNode> expressages = sys.queryAllExpressage(curAccount);
            for (const auto& expressage : expressages) {
                if (expressage.getSendUser() == sys.queryInfo(curAccount).getId()) {
                    cout << "Expressage id: " << expressage.getId() << endl;
                    cout << "Sender: " << expressage.getSendUser() << endl;
                    cout << "Recipient: " << expressage.getReceiveUser() << endl;
                    cout << "Send Time: " << expressage.getAssignTime() << endl;
                    cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                    cout << "Remark: " << expressage.getRemark() << endl;
                }
            }
        } else if (op == "qallr") {
            vector<ExpressageNode> expressages = sys.queryAllExpressage(curAccount);
            for (const auto& expressage : expressages) {
                if (expressage.getReceiveUser() == sys.queryInfo(curAccount).getId()) {
                    cout << "Expressage id: " << expressage.getId() << endl;
                    cout << "Sender: " << expressage.getSendUser() << endl;
                    cout << "Recipient: " << expressage.getReceiveUser() << endl;
                    cout << "Send Time: " << expressage.getAssignTime() << endl;
                    cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                    cout << "Remark: " << expressage.getRemark() << endl;
                }
            }
        } else if (op == "qs") {
            string senderId;
            cin >> senderId;
            vector<ExpressageNode> expressages = sys.queryAllExpressage(curAccount);
            for (const auto& expressage : expressages) {
                if (expressage.getSendUser() == senderId) {
                    cout << "Expressage id: " << expressage.getId() << endl;
                    cout << "Sender: " << expressage.getSendUser() << endl;
                    cout << "Recipient: " << expressage.getReceiveUser() << endl;
                    cout << "Send Time: " << expressage.getAssignTime() << endl;
                    cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                    cout << "Remark: " << expressage.getRemark() << endl;
                }
            }
        } else if (op == "qr") {
            string recipientId;
            cin >> recipientId;
            vector<ExpressageNode> expressages = sys.queryAllExpressage(curAccount);
            for (const auto& expressage : expressages) {
                if (expressage.getReceiveUser() == recipientId) {
                    cout << "Expressage id: " << expressage.getId() << endl;
                    cout << "Sender: " << expressage.getSendUser() << endl;
                    cout << "Recipient: " << expressage.getReceiveUser() << endl;
                    cout << "Send Time: " << expressage.getAssignTime() << endl;
                    cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                    cout << "Remark: " << expressage.getRemark() << endl;
                }
            }
        } else if (op == "qt") {
            string time;
            cin >> time;
            vector<ExpressageNode> expressages = sys.queryAllExpressage(curAccount);
            for (const auto& expressage : expressages) {
                if (expressage.getAssignTime() == time) {
                    cout << "Expressage id: " << expressage.getId() << endl;
                    cout << "Sender: " << expressage.getSendUser() << endl;
                    cout << "Recipient: " << expressage.getReceiveUser() << endl;
                    cout << "Send Time: " << expressage.getAssignTime() << endl;
                    cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                    cout << "Remark: " << expressage.getRemark() << endl;
                }
            }
        } else if (op == "q") {
            string expressageId;
            cin >> expressageId;
            ExpressageNode expressage = sys.queryExpressage(curAccount, expressageId);
            if (!expressage.getId().empty()) {
                cout << "Expressage id: " << expressage.getId() << endl;
                cout << "Sender: " << expressage.getSendUser() << endl;
                cout << "Recipient: " << expressage.getReceiveUser() << endl;
                cout << "Send Time: " << expressage.getAssignTime() << endl;
                cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                cout << "Remark: " << expressage.getRemark() << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    sys.save("data/account.txt", "data/expressage.txt");
    return 0;
}
