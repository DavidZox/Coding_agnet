#include <iostream>
#include <string>
#include <sstream>
#include <vector>
#include <iomanip>
#include <fstream>
#include <algorithm>

#include "include/logistics.h"

using namespace std;

// Function to find user index
int findUserIndex(LogisticSys& sys, const string& username) {
    for (int i = 0; i < sys.account.size(); ++i) {
        if (sys.account[i].id == username) {
            return i;
        }
    }
    return -1; // Not found
}

// Function to handle post-login operations
void handle_post_login(LogisticSys& sys, int current_user_index) {
    string op;
    while (true) {
        cout << "\nEnter operation (cpwd, send, sign, qm, recharge, qall, qalls, qallr, qs, qr, qt, q, exit): ";
        if (!(cin >> op)) break; // Handle EOF

        if (op == "exit") {
            cout << "Bye!" << endl;
            break;
        } else if (op == "cpwd") {
            string old_pwd, new_pwd;
            cout << "Enter old password: "; cin >> old_pwd;
            cout << "Enter new password: "; cin >> new_pwd;
            if (sys.changePassword(current_user_index, old_pwd, new_pwd)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "send") {
            string recipient_user, remark, send_time;
            cout << "Enter recipient username: "; cin >> recipient_user;
            cout << "Enter remark: "; cin >> remark;
            cout << "Enter sending time (yyyy-mm-dd): "; cin >> send_time;

            // Cost is 15 units, deducted from sender, transferred to root account (index 0 if root exists)
            if (sys.assignExpressage(current_user_index, recipient_user, remark, send_time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "sign") {
            string log_id, sign_time;
            cout << "Enter logistics ID: "; cin >> log_id;
            cout << "Enter sign time (yyyy-mm-dd): "; cin >> sign_time;

            if (sys.signExpressage(current_user_index, log_id, sign_time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "qm") {
            double balance = sys.queryMoney(current_user_index);
            cout << "Rest money: " << fixed << setprecision(2) << balance << endl;
        } else if (op == "recharge") {
            double amount;
            cout << "Enter recharge amount: ";
            if (cin >> amount) {
                if (amount < 0) {
                    cout << "Failed." << endl;
                } else {
                    if (sys.addMoney(current_user_index, amount)) {
                        double new_balance = sys.queryMoney(current_user_index);
                        cout << "Rest money: " << fixed << setprecision(2) << new_balance << endl;
                    } else {
                        cout << "Failed." << endl;
                    }
                }
            } else {
                cout << "Invalid input for recharge amount." << endl;
                cin.clear();
                cin.ignore(10000, '\n');
            }
        } else if (op == "qall") {
            // Root/Admin can query all. Normal user queries sender/recipient.
            // Assuming LogisticSys handles authorization internally.
            auto packages = sys.queryAllExpressage(current_user_index);
            if (packages.empty()) {
                cout << "No packages found." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qalls") {
            // Query all sent by current user
            auto packages = sys.queryAllExpressageSentBy(current_user_index);
            if (packages.empty()) {
                cout << "No packages sent by you." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qallr") {
            // Query all received by current user
            auto packages = sys.queryAllExpressageReceivedBy(current_user_index);
            if (packages.empty()) {
                cout << "No packages received by you." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qs") {
            string username_x;
            cout << "Enter username to query sent packages by: "; cin >> username_x;
            auto packages = sys.queryExpressageBySender(current_user_index, username_x);
            if (packages.empty()) {
                cout << "No packages found matching criteria." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qr") {
            string username_x;
            cout << "Enter username to query received packages from: "; cin >> username_x;
            auto packages = sys.queryExpressageByRecipient(current_user_index, username_x);
            if (packages.empty()) {
                cout << "No packages found matching criteria." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qt") {
            string time_t;
            cout << "Enter sending time to query: "; cin >> time_t;
            auto packages = sys.queryExpressageBySendTime(time_t);
            if (packages.empty()) {
                cout << "No packages found matching criteria." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "q") {
            string log_id;
            cout << "Enter logistics ID to query: "; cin >> log_id;
            auto pkg = sys.queryExpressageById(log_id);
            if (pkg.empty()) {
                cout << "Failed." << endl;
            } else {
                const auto& p = pkg[0];
                cout << "Expressage id: " << p.id << endl;
                cout << "Sender: " << p.sendUser << endl;
                cout << "Recipient: " << p.receiveUser << endl;
                cout << "Send Time: " << p.assignTime << endl;
                cout << "Status: " << (p.Flag ? "Delivered" : "Unsigned") << endl;
                cout << "Sign Time: " << (p.signTime == "NULL" ? "NULL" : p.signTime) << endl;
                cout << "Remark: " << p.remark << endl;
            }
        } else {
            cout << "Wrong operation name." << endl;
        }
    }
}

// Function to handle post-login operations
void handle_post_login(LogisticSys& sys, int current_user_index) {
    string op;
    while (true) {
        cout << "\nEnter operation (cpwd, send, sign, qm, recharge, qall, qalls, qallr, qs, qr, qt, q, exit): ";
        if (!(cin >> op)) break; // Handle EOF

        if (op == "exit") {
            cout << "Bye!" << endl;
            break;
        } else if (op == "cpwd") {
            string old_pwd, new_pwd;
            cout << "Enter old password: "; cin >> old_pwd;
            cout << "Enter new password: "; cin >> new_pwd;
            if (sys.changePassword(current_user_index, old_pwd, new_pwd)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "send") {
            string recipient_user, remark, send_time;
            cout << "Enter recipient username: "; cin >> recipient_user;
            cout << "Enter remark: "; cin >> remark;
            cout << "Enter sending time (yyyy-mm-dd): "; cin >> send_time;

            // Cost is 15 units, deducted from sender, transferred to root account (index 0 if root exists)
            if (sys.assignExpressage(current_user_index, recipient_user, remark, send_time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "sign") {
            string log_id, sign_time;
            cout << "Enter logistics ID: "; cin >> log_id;
            cout << "Enter sign time (yyyy-mm-dd): "; cin >> sign_time;

            if (sys.signExpressage(current_user_index, log_id, sign_time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "qm") {
            double balance = sys.queryMoney(current_user_index);
            cout << "Rest money: " << fixed << setprecision(2) << balance << endl;
        } else if (op == "recharge") {
            double amount;
            cout << "Enter recharge amount: ";
            if (cin >> amount) {
                if (amount < 0) {
                    cout << "Failed." << endl;
                } else {
                    if (sys.addMoney(current_user_index, amount)) {
                        double new_balance = sys.queryMoney(current_user_index);
                        cout << "Rest money: " << fixed << setprecision(2) << new_balance << endl;
                    } else {
                        cout << "Failed." << endl;
                    }
                }
            } else {
                cout << "Invalid input for recharge amount." << endl;
                cin.clear();
                cin.ignore(10000, '\n');
            }
        } else if (op == "qall") {
            // Root/Admin can query all. Normal user queries sender/recipient.
            // Assuming LogisticSys handles authorization internally.
            auto packages = sys.queryAllExpressage(current_user_index);
            if (packages.empty()) {
                cout << "No packages found." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qalls") {
            // Query all sent by current user
            auto packages = sys.queryAllExpressageSentBy(current_user_index);
            if (packages.empty()) {
                cout << "No packages sent by you." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qallr") {
            // Query all received by current user
            auto packages = sys.queryAllExpressageReceivedBy(current_user_index);
            if (packages.empty()) {
                cout << "No packages received by you." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qs") {
            string username_x;
            cout << "Enter username to query sent packages by: "; cin >> username_x;
            auto packages = sys.queryExpressageBySender(current_user_index, username_x);
            if (packages.empty()) {
                cout << "No packages found matching criteria." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qr") {
            string username_x;
            cout << "Enter username to query received packages from: "; cin >> username_x;
            auto packages = sys.queryExpressageByRecipient(current_user_index, username_x);
            if (packages.empty()) {
                cout << "No packages found matching criteria." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "qt") {
            string time_t;
            cout << "Enter sending time to query: "; cin >> time_t;
            auto packages = sys.queryExpressageBySendTime(time_t);
            if (packages.empty()) {
                cout << "No packages found matching criteria." << endl;
            } else {
                for (const auto& pkg : packages) {
                    cout << "Expressage id: " << pkg.id << endl;
                    cout << "Sender: " << pkg.sendUser << endl;
                    cout << "Recipient: " << pkg.receiveUser << endl;
                    cout << "Send Time: " << pkg.assignTime << endl;
                    cout << "Status: " << (pkg.Flag ? "Delivered" : "Unsigned") << endl;
                    cout << "Sign Time: " << (pkg.signTime == "NULL" ? "NULL" : pkg.signTime) << endl;
                    cout << "Remark: " << pkg.remark << endl;
                }
            }
        } else if (op == "q") {
            string log_id;
            cout << "Enter logistics ID to query: "; cin >> log_id;
            auto pkg = sys.queryExpressageById(log_id);
            if (pkg.empty()) {
                cout << "Failed." << endl;
            } else {
                const auto& p = pkg[0];
                cout << "Expressage id: " << p.id << endl;
                cout << "Sender: " << p.sendUser << endl;
                cout << "Recipient: " << p.receiveUser << endl;
                cout << "Send Time: " << p.assignTime << endl;
                cout << "Status: " << (p.Flag ? "Delivered" : "Unsigned") << endl;
                cout << "Sign Time: " << (p.signTime == "NULL" ? "NULL" : p.signTime) << endl;
                cout << "Remark: " << p.remark << endl;
            }
        } else {
            cout << "Wrong operation name." << endl;
        }
    }
}


int main() {
    // 1. Initialize LogisticSys
    LogisticSys sys;
    
    // 2. Load data from files
    // Assuming init() handles reading data/account.txt and data/expressage.txt
    sys.init("data/account.txt", "data/expressage.txt");

    int current_user_index = -1;
    bool logged_in = false;

    // --- Phase 1: Pre-Login Operations ---
    while (!logged_in) {
        string op;
        cout << "Enter operation (reg, login, exit): ";
        if (!(cin >> op)) break;

        if (op == "exit") {
            cout << "Bye!" << endl;
            break;
        } else if (op == "reg") {
            string username, password, name, phone, address;
            cout << "Enter username: "; cin >> username;
            cout << "Enter password: "; cin >> password;
            cout << "Enter name: "; cin >> name;
            cout << "Enter phone number: "; cin >> phone;
            cout << "Enter address: "; cin >> address;

            // PRD requires 5 strings for registration: username, password, name, phone number, and address.
            // UML_class.md suggests Regist(string, string, string, string, double, string)
            // We use 0.0 for money and 2 for normal user type as per PRD example structure.
            if (sys.Regist(username, password, name, phone, 0.0, address, 2)) { 
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "login") {
            string username, password;
            cout << "Enter username: "; cin >> username;
            cout << "Enter password: "; cin >> password;

            if (sys.Login(username, password)) {
                cout << "Welcome!" << endl;
                
                // Output user info after successful login
                // Replaced sys.findUserIndex(username) with manual search logic
                int index = findUserIndex(sys, username); 
                
                if (index != -1) {
                    auto user_info = sys.queryInfo(index); 
                    if (!user_info.empty()) {
                        const auto& user = user_info[0];
                        cout << "AccountId: " << user.id << endl;
                        cout << "UserName: " << user.name << endl;
                        cout << "UserPhone: " << user.phone << endl;
                        cout << "Money: " << fixed << setprecision(2) << user.money << endl;
                        cout << "Address: " << user.address << endl;
                        // Map authority type (0/1/2) to string
                        string user_type_str;
                        if (user.type == 0) user_type_str = "root";
                        else if (user.type == 1) user_type_str = "admin";
                        else user_type_str = "normal user";
                        cout << "UserType: " << user_type_str << endl;
                    }
                    current_user_index = index;
                    logged_in = true;
                } else {
                    // Should not happen if Login succeeded, but for safety
                    cout << "Error: User found in login but not in account list." << endl;
                }
            } else {
                cout << "Wrong account id or/and password." << endl;
            }
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    // --- Phase 2: Post-Login Operations ---
    if (logged_in) {
        handle_post_login(sys, current_user_index);
    }

    // 3. Save data before exiting
    sys.save("data/account.txt", "data/expressage.txt");

    return 0;
}
