#include <iostream>
#include <string>
#include <vector>
#include <iomanip>
#include "logistics.h"

using namespace std;

void printUserInfo(const AccountNode& acc) {
    string typeStr;
    if (acc.type == authority::root) typeStr = "root";
    else if (acc.type == authority::admin) typeStr = "admin";
    else typeStr = "normal user";

    cout << "AccountId: " << acc.id << "\n";
    cout << "UserName: " << acc.name << "\n";
    cout << "UserPhone: " << acc.phone << "\n";
    // To match unit test "Money: 100" for 100.0, default stream behavior is used
    cout << "Money: " << acc.money << "\n";
    cout << "Address: " << acc.address << "\n";
    cout << "UserType: " << typeStr << endl;
}

int main() {
    LogisticSys sys;
    sys.init("data/account.txt", "data/expressage.txt");

    string op;
    int currentIdx = -1;

    // Phase 1: Before Successful Login
    while (true) {
        if (!(cin >> op)) break;

        if (op == "reg") {
            string id, pwd, nm, ph, ad;
            cin >> id >> pwd >> nm >> ph >> ad;
            if (sys.Regist(id, pwd, nm, ph, 0.0, ad)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "login") {
            string id, pwd;
            cin >> id >> pwd;
            int idx = sys.Login(id, pwd);
            if (idx != -1) {
                currentIdx = idx;
                cout << "Welcome!" << endl;
                printUserInfo(sys.queryInfo(currentIdx));
                break;
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

    // Phase 2: After Successful Login
    while (true) {
        if (!(cin >> op)) break;

        if (op == "cpwd") {
            string oldpwd, newpwd;
            cin >> oldpwd >> newpwd;
            if (sys.changePassword(currentIdx, oldpwd, newpwd)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "exit") {
            sys.save("data/account.txt", "data/expressage.txt");
            cout << "Bye!" << endl;
            break;
        } else if (op == "send") {
            string receiverId, remark, time;
            cin >> receiverId >> remark >> time;
            if (sys.assignExpressage(currentIdx, receiverId, remark, time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "sign") {
            string id, time;
            cin >> id >> time;
            if (sys.signExpressage(currentIdx, id, time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "qm") {
            double money = sys.queryMoney(currentIdx);
            cout << "Rest money: " << fixed << setprecision(2) << money << endl;
            // Note: The PRD says "rounded to two decimal places", but the unit test 
            // for AccountNode uses default stream. However, qm is a specific command.
            // To be safe with "Rest money: money" format:
            // We use fixed/setprecision(2) as requested by PRD.
        } else if (op == "recharge") {
            double amount;
            cin >> amount;
            if (amount < 0) {
                cout << "Failed." << endl;
            } else {
                double newMoney = sys.addMoney(currentIdx, amount);
                cout << "Rest money: " << fixed << setprecision(2) << newMoney << endl;
            }
        } else if (op == "qall") {
            auto list = sys.queryAllExpressage(currentIdx);
            for (auto& e : list) cout << e;
        } else if (op == "qalls") {
            // qalls is a subset of qall (only sent by current user)
            // Since queryAllExpressage returns all related, we filter manually
            auto all = sys.queryAllExpressage(currentIdx);
            string myId = sys.queryInfo(currentIdx).id;
            for (auto& e : all) {
                if (e.sendUser == myId) cout << e;
            }
        } else if (op == "qallr") {
            // qallr is a subset of qall (only received by current user)
            auto all = sys.queryAllExpressage(currentIdx);
            string myId = sys.queryInfo(currentIdx).id;
            for (auto& e : all) {
                if (e.receiveUser == myId) cout << e;
            }
        } else if (op == "qs") {
            string x;
            cin >> x;
            auto all = sys.queryAllExpressage(currentIdx);
            string myId = sys.queryInfo(currentIdx).id;
            for (auto& e : all) {
                if (e.sendUser == x && (e.sendUser == myId || e.receiveUser == myId)) cout << e;
            }
        } else if (op == "qr") {
            string x;
            cin >> x;
            auto all = sys.queryAllExpressage(currentIdx);
            string myId = sys.queryInfo(currentIdx).id;
            for (auto& e : all) {
                if (e.receiveUser == x && (e.sendUser == myId || e.receiveUser == myId)) cout << e;
            }
        } else if (op == "qt") {
            string t;
            cin >> t;
            auto all = sys.queryAllExpressage(currentIdx);
            for (auto& e : all) {
                if (e.assignTime == t) cout << e;
            }
        } else if (op == "q") {
            string id;
            cin >> id;
            auto e = sys.queryExpressage(currentIdx, id);
            if (e.id == "") cout << "Failed." << endl;
            else cout << e;
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    return 0;
}
