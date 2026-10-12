#include <iostream>
#include <string>
#include <vector>
#include <iomanip>
#include "account.h"
#include "expressage.h"
#include "logistics.h"

using namespace std;

string typeToString(int type) {
    if (type == 0) return "root";
    if (type == 1) return "admin";
    return "normal user";
}

int main() {
    LogisticSys sys;
    sys.init("data/account.txt", "data/expressage.txt");

    string op;
    bool loggedIn = false;
    int currentUserId = -1;

    // Phase 1: Before Successful Login
    while (true) {
        if (!(cin >> op)) break;

        if (op == "reg") {
            string id, pwd, name, phone, addr;
            cin >> id >> pwd >> name >> phone >> addr;
            // According to UML/PRD, Regist takes (id, pwd, name, phone, money, addr)
            // For registration, money is 0
            if (sys.Regist(id, pwd, name, phone, 0.0, addr)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "login") {
            string id, pwd;
            cin >> id >> pwd;
            int idx = sys.Login(id, pwd);
            if (idx != -1) {
                loggedIn = true;
                currentUserId = idx;
                cout << "Welcome!" << endl;
                
                // Print User Info
                AccountNode info = sys.queryInfo(currentUserId);
                cout << "AccountId: " << info.getId() << endl;
                cout << "UserName: " << info.getName() << endl;
                cout << "UserPhone: " << info.getPhone() << endl;
                // PRD example shows Money: 100 (no decimals if integer), but balance is real.
                // To match "Money: 100" while allowing decimals if needed, we use a simple approach.
                // However, the most robust way to match the example "Money: 100" is to check if it's an integer.
                // But since the requirement is simple, we'll use a logic that outputs 100 for 100.0.
                // Given the constraints, let's use a logic that outputs 100 for 100.0.
                double m = info.getMoney();
                if (m == (long long)m) cout << "Money: " << (long long)m << endl;
                else cout << "Money: " << m << endl;

                cout << "Address: " << info.getAddress() << endl;
                cout << "UserType: " << typeToString(info.getType()) << endl;
                
                // Break the Phase 1 loop to enter Phase 2
                break;
            } else {
                cout << "Wrong account id or/and password." << endl;
            }
        } else if (op == "exit") {
            cout << "Bye!" << endl;
            sys.save("data/account.txt", "data/expressage.txt");
            return 0;
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    // Phase 2: After Successful Login
    if (loggedIn) {
        while (true) {
            if (!(cin >> op)) break;

            if (op == "exit") {
                cout << "Bye!" << endl;
                sys.save("data/account.txt", "data/expressage.txt");
                return 0;
            } else if (op == "cpwd") {
                string old_pwd, new_pwd;
                cin >> old_pwd >> new_pwd;
                if (sys.changePassword(currentUserId, old_pwd, new_pwd)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "send") {
                string receiverId, remark, time;
                cin >> receiverId >> remark >> time;
                if (sys.assignExpressage(currentUserId, receiverId, remark, time)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "sign") {
                string exId, time;
                cin >> exId >> time;
                if (sys.signExpressage(currentUserId, exId, time)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            } else if (op == "qm") {
                double money = sys.queryMoney(currentUserId);
                cout << "Rest money: " << fixed << setprecision(2) << money << endl;
            } else if (op == "recharge") {
                double amount;
                cin >> amount;
                if (amount < 0) {
                    cout << "Failed." << endl;
                } else {
                    double new_money = sys.addMoney(currentUserId, amount);
                    cout << "Rest money: " << fixed << setprecision(2) << new_money << endl;
                }
            } else if (op == "qall") {
                vector<ExpressageNode> res = sys.queryAllExpressage(currentUserId);
                for (const auto& e : res) cout << e << endl;
            } else if (op == "qalls") {
                // PRD: Query all packages sent by the current user.
                // Since LogisticSys doesn't have a specific method, we filter the results of queryAllExpressage.
                // However, queryAllExpressage for a normal user already returns only their related packages.
                // To strictly follow "sent by current user", we'd need to check the sender.
                // But we can't access sender from ExpressageNode easily without a getter.
                // Assuming queryAllExpressage returns all relevant ones, we'll use it.
                // If the system provides a way to get sender, we'd use it. 
                // Given the constraints, we'll output the results of queryAllExpressage.
                vector<ExpressageNode> all = sys.queryAllExpressage(currentUserId);
                AccountNode cur = sys.queryInfo(currentUserId);
                string myId = cur.getId();
                for (const auto& e : all) {
                    if (e.getSendUser() == myId) {
                        cout << e << endl;
                    }
                }
            } else if (op == "qallr") {
                vector<ExpressageNode> all = sys.queryAllExpressage(currentUserId);
                AccountNode cur = sys.queryInfo(currentUserId);
                string myId = cur.getId();
                for (const auto& e : all) {
                    if (e.getReceiveUser() == myId) {
                        cout << e << endl;
                    }
                }
            } else if (op == "qs") {
                string x;
                cin >> x;
                // qs: query all packages related to current user sent by user x
                vector<ExpressageNode> all = sys.queryAllExpressage(currentUserId);
                for (const auto& e : all) {
                    if (e.getSendUser() == x) {
                        cout << e << endl;
                    }
                }
            } else if (op == "qr") {
                string x;
                cin >> x;
                // qr: query all packages related to current user received from user x
                vector<ExpressageNode> all = sys.queryAllExpressage(currentUserId);
                for (const auto& e : all) {
                    if (e.getSendUser() == x) {
                        cout << e << endl;
                    }
                }
            } else if (op == "qt") {
                string t;
                cin >> t;
                // qt: query all packages with a sending time of t
                vector<ExpressageNode> all = sys.queryAllExpressage(currentUserId);
                for (const auto& e : all) {
                    if (e.getAssignTime() == t) {
                        cout << e << endl;
                    }
                }
            } else if (op == "q") {
                string id;
                cin >> id;
                try {
                    ExpressageNode e = sys.queryExpressage(currentUserId, id);
                    cout << e << endl;
                } catch (...) {
                    cout << "Failed." << endl;
                }
            } else {
                cout << "Wrong operation name." << endl;
            }
        }
    }

    cout << "Bye!" << endl;
    sys.save("data/account.txt", "data/expressage.txt");
    return 0;
}
