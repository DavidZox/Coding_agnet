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
        cout << "Enter operation (reg/login/exit): ";
        cin >> op;
        if (op == "reg") {
            string id, pwd, name, phone, address;
            cout << "Enter username: ";
            cin >> id;
            cout << "Enter password: ";
            cin >> pwd;
            cout << "Enter name: ";
            cin >> name;
            cout << "Enter phone number: ";
            cin >> phone;
            cout << "Enter address: ";
            cin >> address;
            if (sys.Regist(id, pwd, name, phone, 0, address)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "login") {
            string id, pwd;
            cout << "Enter username: ";
            cin >> id;
            cout << "Enter password: ";
            cin >> pwd;
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
                if (info.getType() == authority::root) cout << "root" << endl;
                else if (info.getType() == authority::admin) cout << "admin" << endl;
                else cout << "normal user" << endl;
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
        cout << "Enter operation (cpwd/send/sign/qm/recharge/qall/qalls/qallr/qs/qr/qt/q/exit): ";
        cin >> op;
        if (op == "cpwd") {
            string opwd, pwd;
            cout << "Enter old password: ";
            cin >> opwd;
            cout << "Enter new password: ";
            cin >> pwd;
            if (sys.changePassword(curAccount, opwd, pwd)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "send") {
            string receiverId, remark, time;
            cout << "Enter recipient username: ";
            cin >> receiverId;
            cout << "Enter note: ";
            cin >> remark;
            cout << "Enter sending time (yyyy-mm-dd): ";
            cin >> time;
            if (sys.assignExpressage(curAccount, receiverId, remark, time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "sign") {
            string expressageId, time;
            cout << "Enter logistics ID: ";
            cin >> expressageId;
            cout << "Enter sign time (yyyy-mm-dd): ";
            cin >> time;
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
            cout << "Enter recharge amount: ";
            cin >> amount;
            if (amount >= 0) {
                double money = sys.addMoney(curAccount, amount);
                cout << "Rest money: " << fixed << setprecision(2) << money << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "qall" || op == "qalls" || op == "qallr" || op == "qs" || op == "qr" || op == "qt" || op == "q") {
            vector<ExpressageNode> expressages;
            if (op == "qall") {
                expressages = sys.queryAllExpressage(curAccount);
            } else if (op == "qalls") {
                expressages = sys.queryAllExpressage(curAccount);
                // Additional filtering for sent packages can be done here if needed
            } else if (op == "qallr") {
                expressages = sys.queryAllExpressage(curAccount);
                // Additional filtering for received packages can be done here if needed
            } else if (op == "qs" || op == "qr") {
                string username;
                cout << "Enter username: ";
                cin >> username;
                expressages = sys.queryAllExpressage(curAccount);
                // Additional filtering for packages sent or received from a specific user can be done here if needed
            } else if (op == "qt") {
                string time;
                cout << "Enter time (yyyy-mm-dd): ";
                cin >> time;
                expressages = sys.queryAllExpressage(curAccount);
                // Additional filtering for packages with a specific sending time can be done here if needed
            } else if (op == "q") {
                string expressageId;
                cout << "Enter logistics ID: ";
                cin >> expressageId;
                ExpressageNode expressage = sys.queryExpressage(curAccount, expressageId);
                if (expressage.getId().empty()) {
                    cout << "Failed." << endl;
                } else {
                    cout << "Expressage id: " << expressage.getId() << endl;
                    cout << "Sender: " << expressage.getSendUser() << endl;
                    cout << "Recipient: " << expressage.getReceiveUser() << endl;
                    cout << "Send Time: " << expressage.getAssignTime() << endl;
                    cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                    cout << "Remark: " << expressage.getRemark() << endl;
                }
                continue;
            }
            for (const auto& expressage : expressages) {
                cout << "Expressage id: " << expressage.getId() << endl;
                cout << "Sender: " << expressage.getSendUser() << endl;
                cout << "Recipient: " << expressage.getReceiveUser() << endl;
                cout << "Send Time: " << expressage.getAssignTime() << endl;
                cout << "Status: " << (expressage.getFlag() ? "Delivered" : "Unsigned") << endl;
                cout << "Sign Time: " << (expressage.getSignTime().empty() ? "NULL" : expressage.getSignTime()) << endl;
                cout << "Remark: " << expressage.getRemark() << endl;
            }
        } else if (op == "exit") {
            loggedIn = false;
            cout << "Bye!" << endl;
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    sys.save("data/account.txt", "data/expressage.txt");
    return 0;
}
