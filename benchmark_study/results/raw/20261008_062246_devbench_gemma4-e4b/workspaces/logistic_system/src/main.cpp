#include <iostream>
#include <string>
#include <sstream>
#include <iomanip>
#include "logistics.h" // Corrected include path

using namespace std;

// Note: The original file had duplicate includes, keeping the structure as provided but ensuring necessary headers are present.

int main() {
    // 1. Initialization and Data Loading
    LogisticSys sys;
    // PRD: At the start of the program, it needs to read the existing account and logistics information from the files.
    sys.init("data/account.txt", "data/expressage.txt");

    // 2. Before Successful Login Phase
    string op_initial;
    int current_user_index = -1;
    bool logged_in = false;

    while (true) {
        cout << "Enter operation (reg/login/exit): ";
        if (!(cin >> op_initial)) break; // EOF

        if (op_initial == "exit") {
            cout << "Bye!" << endl;
            break;
        } else if (op_initial == "reg") {
            string username, password, name, phone, address;
            if (cin >> username >> password >> name >> phone >> address) {
                // PRD: Reads 5 strings: username, password, name, phone number, and address.
                // Assuming default balance 0.0 and user type 2 (normal) for registration based on PRD input structure.
                if (sys.Regist(username, password, name, phone, 0.0, address)) {
                    cout << "Succeed." << endl;
                } else {
                    cout << "Failed." << endl;
                }
            }
        } else if (op_initial == "login") {
            string username, password;
            if (cin >> username >> password) {
                // PRD: Login returns an index (-1 on failure)
                int index = sys.Login(username, password);
                if (index != -1) {
                    cout << "Welcome!" << endl;
                    current_user_index = index;
                    logged_in = true;
                    break; // Exit initial loop, proceed to after login phase
                } else {
                    cout << "Wrong account id or/and password." << endl;
                }
            }
        } else {
            cout << "Wrong operation name." << endl;
        }
    }

    // 3. After Successful Login Phase
    if (logged_in) {
        // Output current user information
        sys.queryInfo(current_user_index);

        // Continuous operation loop
        string op_after;
        while (cin >> op_after) {
            if (op_after == "exit") {
                cout << "Bye!" << endl;
                break;
            }
            
            if (op_after == "cpwd") {
                string old_pwd, new_pwd;
                if (cin >> old_pwd >> new_pwd) {
                    if (sys.changePassword(current_user_index, old_pwd, new_pwd)) {
                        cout << "Succeed." << endl;
                    } else {
                        cout << "Failed." << endl;
                    }
                }
            } else if (op_after == "send") {
                string recipient_user, remark, send_time;
                // PRD: Reads three strings: recipient's username, a note, and the sending time.
                if (cin >> recipient_user >> remark >> send_time) {
                    // Cost is 15 units.
                    if (sys.assignExpressage(current_user_index, recipient_user, remark, send_time)) {
                        cout << "Succeed." << endl;
                    } else {
                        cout << "Failed." << endl;
                    }
                }
            } else if (op_after == "sign") {
                string logistics_id, sign_time;
                if (cin >> logistics_id >> sign_time) {
                    if (sys.signExpressage(current_user_index, logistics_id, sign_time)) {
                        cout << "Succeed." << endl;
                    } else {
                        cout << "Failed." << endl;
                    }
                }
            } else if (op_after == "qm") {
                // PRD: Output current user's balance rounded to two decimal places.
                double balance = sys.queryMoney(current_user_index);
                cout << "Rest money: " << fixed << setprecision(2) << balance << endl;
            } else if (op_after == "recharge") {
                double amount;
                if (cin >> amount) {
                    if (amount >= 0) {
                        if (sys.addMoney(current_user_index, amount)) {
                            // Output balance after recharge
                            double balance = sys.queryMoney(current_user_index);
                            cout << "Rest money: " << fixed << setprecision(2) << balance << endl;
                        } else {
                            cout << "Failed." << endl;
                        }
                    } else {
                        cout << "Failed." << endl;
                    }
                }
            } else if (op_after == "qall") {
                // Query all packages related to the current user.
                sys.queryAllExpressage(current_user_index);
            } else if (op_after == "qalls") {
                // Query all packages sent by the current user.
                // Modification: Fetch current user's username to match signature: queryAllSent(int accountIndex, std::string senderUsername)
                AccountNode current_account = sys.queryInfo(current_user_index);
                sys.queryAllSent(current_user_index, current_account.getName());
            } else if (op_after == "qallr") {
                // Query all packages received by the current user.
                // Modification: Fetch current user's username to match signature: queryAllReceived(int accountIndex, std::string recipientUsername)
                AccountNode current_account = sys.queryInfo(current_user_index);
                sys.queryAllReceived(current_user_index, current_account.getName());
            } else if (op_after == "qs") {
                // Query all packages sent by user x.
                string sender_user;
                if (cin >> sender_user) {
                    // Modification: Match signature: queryAllSent(int accountIndex, std::string senderUsername)
                    sys.queryAllSent(current_user_index, sender_user);
                }
            } else if (op_after == "qr") {
                // Query all packages received from user x.
                string receiver_user;
                if (cin >> receiver_user) {
                    // Modification: Match signature: queryAllReceived(int accountIndex, std::string recipientUsername)
                    sys.queryAllReceived(current_user_index, receiver_user);
                }
            } else if (op_after == "qt") {
                // Query all packages with a sending time of t.
                string send_time;
                if (cin >> send_time) {
                    sys.queryByTime(current_user_index, send_time);
                }
            } else if (op_after == "q") {
                // Query package by ID.
                string logistics_id;
                if (cin >> logistics_id) {
                    sys.queryExpressage(current_user_index, logistics_id);
                }
            } else {
                cout << "Wrong operation name." << endl;
            }
        }
    }

    // 4. Final Save
    // PRD: At the end of the program, it needs to write the current account and logistics information to the files.
    sys.save("data/account.txt", "data/expressage.txt");

    return 0;
}
