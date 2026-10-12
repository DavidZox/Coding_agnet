#include <iostream>
#include <string>
#include <sstream>
#include <iomanip>
#include <limits>

#include "logistics.h"
#include "account.h"
#include "expressage.h"

using namespace std;

// Global instance of the system manager
LogisticSys system;

// Function prototypes
void handle_pre_login_operation(string& op);
void handle_post_login_operation(int& current_account_index);
void display_user_info(const AccountNode& acc);
void display_expressage_details(const ExpressageNode& exp);

int main() {
    // Initialize system (assuming default file paths based on PRD)
    system.init("data/account.txt", "data/expressage.txt");

    string op;
    int current_account_index = -1;

    // --- Phase 1: Before Successful Login ---
    cout << "--- Logistics Management System Initializing ---" << endl;
    while (true) {
        cout << "Enter operation (reg/login/exit): ";
        if (!(cin >> op)) break;

        if (op == "exit") {
            cout << "Bye!" << endl;
            system.save("data/account.txt", "data/expressage.txt");
            break;
        } else if (op == "reg") {
            // Registration logic
            string username, password, name, phone, address;
            double initial_money = 0.0;
            
            cout << "Enter username: "; cin >> username;
            cout << "Enter password: "; cin >> password;
            cout << "Enter name: "; cin >> name;
            cout << "Enter phone number: "; cin >> phone;
            cout << "Enter address: "; cin >> address;

            if (system.Regist(username, password, name, phone, initial_money, address)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        } else if (op == "login") {
            // Login logic
            string username, password;
            cout << "Enter username: "; cin >> username;
            cout << "Enter password: "; cin >> password;

            int index = system.Login(username, password);
            if (index != -1) {
                cout << "Welcome!" << endl;
                current_account_index = index;
                break; // Exit pre-login loop, enter post-login phase
            } else {
                cout << "Wrong account id or/and password." << endl;
            }
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    // --- Phase 2: After Successful Login ---
    if (current_account_index != -1) {
        handle_post_login_operation(current_account_index);
    }

    // Save data before final exit
    system.save("data/account.txt", "data/expressage.txt");
    return 0;
}

void display_user_info(const AccountNode& acc) {
    cout << "AccountId: " << acc.getId() << endl;
    cout << "UserName: " << acc.getName() << endl;
    cout << "UserPhone: " << acc.getPhone() << endl;
    cout << "Money: " << fixed << setprecision(2) << acc.getMoney() << endl;
    cout << "Address: " << acc.getAddress() << endl;
    
    string type_str;
    switch (acc.getType()) {
        case root: type_str = "root"; break;
        case admin: type_str = "admin"; break;
        case user: type_str = "normal user"; break;
    }
    cout << "UserType: " << type_str << endl;
}

void display_expressage_details(const ExpressageNode& exp) {
    // Output format matching the requirement for query results
    cout << "Expressage id: " << exp.id << endl;
    cout << "Sender: " << exp.sendUser << endl;
    cout << "Recipient: " << exp.receiveUser << endl;
    cout << "Send Time: " << exp.assignTime << endl;
    
    string status_str = exp.Flag ? "Delivered" : "Unsigned";
    cout << "Status: " << status_str << endl;
    
    string sign_time_out = exp.signTime.empty() ? "NULL" : exp.signTime;
    cout << "Sign Time: " << sign_time_out << endl;
    
    cout << "Remark: " << exp.remark << endl;
}


void handle_post_login_operation(int& current_account_index) {
    // Initial display after successful login
    AccountNode initial_info = system.queryInfo(current_account_index);
    display_user_info(initial_info);

    string op;
    while (true) {
        cout << "\nEnter operation (cpwd/exit/send/sign/qm/recharge/qall/qalls/qallr/qs/qr/qt/q): ";
        if (!(cin >> op)) break;

        if (op == "exit") {
            cout << "Bye!" << endl;
            break;
        } 
        // --- Password Change ---
        else if (op == "cpwd") {
            string old_pwd, new_pwd;
            cout << "Enter old password: "; cin >> old_pwd;
            cout << "Enter new password: "; cin >> new_pwd;
            if (system.changePassword(current_account_index, old_pwd, new_pwd)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        }
        // --- Send Package ---
        else if (op == "send") {
            string receiver_id, remark, send_time;
            cout << "Enter recipient username: "; cin >> receiver_id;
            cout << "Enter remark: "; cin >> remark;
            cout << "Enter sending time (yyyy-mm-dd): "; cin >> send_time;

            if (system.assignExpressage(current_account_index, receiver_id, remark, send_time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        }
        // --- Sign Package ---
        else if (op == "sign") {
            string log_id, sign_time;
            cout << "Enter logistics ID: "; cin >> log_id;
            cout << "Enter sign time (yyyy-mm-dd): "; cin >> sign_time;

            if (system.signExpressage(current_account_index, log_id, sign_time)) {
                cout << "Succeed." << endl;
            } else {
                cout << "Failed." << endl;
            }
        }
        // --- Check Balance ---
        else if (op == "qm") {
            double money = system.queryMoney(current_account_index);
            cout << "Rest money: " << fixed << setprecision(2) << money << endl;
        }
        // --- Recharge ---
        else if (op == "recharge") {
            double amount;
            cout << "Enter recharge amount: "; cin >> amount;
            if (amount >= 0) {
                double new_money = system.addMoney(current_account_index, amount);
                cout << "Rest money: " << fixed << setprecision(2) << new_money << endl;
            } else {
                cout << "Failed." << endl;
            }
        }
        // --- Query All (Sender/Recipient) ---
        else if (op == "qall") {
            vector<ExpressageNode> results = system.queryAllExpressage(current_account_index);
            if (results.empty()) {
                cout << "No packages found matching criteria." << endl;
            } else {
                for (const auto& exp : results) {
                    cout << "\n--- Package Details ---" << endl;
                    display_expressage_details(exp);
                }
            }
        }
        // --- Query All Sent By ---
        else if (op == "qalls") {
            // Note: The current implementation of queryAllExpressage handles sender/recipient filtering based on user type.
            // To strictly implement qalls (sent by current user), we would need a dedicated function in LogisticSys.
            // Since the specification implies queryAllExpressage handles the filtering logic based on user type, 
            // we rely on that, but for strict adherence, we assume qalls implies filtering by sender ID.
            // For this implementation, we will treat qalls as a specific filter if possible, otherwise, rely on the general query.
            // Given the constraints, we'll use queryAllExpressage and rely on the system logic to filter correctly if possible, 
            // or assume the system handles the sender filter internally if the user is normal.
            // Since LogisticSys doesn't expose a specific 'querySentBy' method, we'll simulate by querying all and filtering locally if necessary, 
            // but for simplicity matching the provided structure, we call queryAllExpressage and assume the system handles the intent.
            // A robust solution would require adding a specific query method to LogisticSys.
            
            // For now, we call queryAllExpressage and rely on the system's internal logic to handle the intent if the user is normal.
            vector<ExpressageNode> results = system.queryAllExpressage(current_account_index);
            cout << "--- Packages Sent By Current User ---" << endl;
            for (const auto& exp : results) {
                if (exp.sendUser == system.queryInfo(current_account_index).getId()) {
                    cout << "\n--- Package Details ---" << endl;
                    display_expressage_details(exp);
                }
            }
        }
        // --- Query All Received By ---
        else if (op == "qallr") {
            vector<ExpressageNode> results = system.queryAllExpressage(current_account_index);
            cout << "--- Packages Received By Current User ---" << endl;
            for (const auto& exp : results) {
                if (exp.receiveUser == system.queryInfo(current_account_index).getId()) {
                    cout << "\n--- Package Details ---" << endl;
                    display_expressage_details(exp);
                }
            }
        }
        // --- Query By Sender Username ---
        else if (op == "qs") {
            string sender_username;
            cout << "Enter sender username: "; cin >> sender_username;
            vector<ExpressageNode> results = system.queryAllExpressage(current_account_index);
            cout << "--- Packages Sent By " << sender_username << " ---" << endl;
            for (const auto& exp : results) {
                if (exp.sendUser == sender_username) {
                    cout << "\n--- Package Details ---" << endl;
                    display_expressage_details(exp);
                }
            }
        }
        // --- Query By Recipient Username ---
        else if (op == "qr") {
            string receiver_username;
            cout << "Enter recipient username: "; cin >> receiver_username;
            vector<ExpressageNode> results = system.queryAllExpressage(current_account_index);
            cout << "--- Packages Received By " << receiver_username << " ---" << endl;
            for (const auto& exp : results) {
                if (exp.receiveUser == receiver_username) {
                    cout << "\n--- Package Details ---" << endl;
                    display_expressage_details(exp);
                }
            }
        }
        // --- Query By Send Time ---
        else if (op == "qt") {
            string send_time;
            cout << "Enter send time (yyyy-mm-dd): "; cin >> send_time;
            vector<ExpressageNode> results = system.queryAllExpressage(current_account_index);
            cout << "--- Packages Sent On " << send_time << " ---" << endl;
            for (const auto& exp : results) {
                if (exp.assignTime == send_time) {
                    cout << "\n--- Package Details ---" << endl;
                    display_expressage_details(exp);
                }
            }
        }
        // --- Query By Logistics ID ---
        else if (op == "q") {
            string log_id;
            cout << "Enter logistics ID: "; cin >> log_id;
            ExpressageNode exp = system.queryExpressage(current_account_index, log_id);
            if (exp.id.empty()) {
                cout << "Failed." << endl;
            } else {
                cout << "\n--- Package Details ---" << endl;
                display_expressage_details(exp);
            }
        }
        else {
            cout << "Wrong operation name." << endl;
        }
    }
}
