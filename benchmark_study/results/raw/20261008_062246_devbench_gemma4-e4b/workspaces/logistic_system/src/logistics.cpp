#include "logistics.h"
#include "account.h"
#include "expressage.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <algorithm>

using namespace std;

// Helper function to convert user type enum to string for output
string accountTypeToString(authority type) {
    if (type == authority::root) return "root";
    if (type == authority::admin) return "admin";
    return "normal user";
}

// Helper function to convert string to user type enum
authority stringToAuthority(const string& typeStr) {
    if (typeStr == "0") return authority::root;
    if (typeStr == "1") return authority::admin;
    if (typeStr == "2") return authority::normal_user;
    return authority::normal_user; // Default fallback
}

// Helper function to generate Logistics ID
string generateLogisticsId(int count) {
    stringstream ss;
    ss << "KD" << setfill('0') << setw(8) << count;
    return ss.str();
}

// --- LogisticSys Implementation ---

LogisticSys::LogisticSys() : accountNum(0), expressageNum(0), rootIndex(-1) {}

LogisticSys::~LogisticSys() {}

// Initialization: Reads data from files
void LogisticSys::init(std::string accountFile, std::string expressageFile) {
    // 1. Load Accounts
    ifstream accFile(accountFile);
    if (!accFile.is_open()) {
        cerr << "Warning: Could not open account file: " << accountFile << endl;
        return;
    }

    string line;
    if (getline(accFile, line)) {
        try {
            accountNum = stoi(line);
        } catch (...) {
            accountNum = 0;
        }
    }

    account.clear();
    for (int i = 0; i < accountNum; ++i) {
        if (getline(accFile, line)) {
            stringstream ss(line);
            string id, password, name, phone, address, typeStr;
            double money;
            
            // Format: username password name phone number address user_type
            ss >> id >> password >> name >> phone >> money >> address >> typeStr;
            
            authority type = stringToAuthority(typeStr);
            AccountNode node(id, password, name, phone, money, address, type);
            account.push_back(node);
        }
    }
    accFile.close();

    // Find root index
    for (size_t i = 0; i < account.size(); ++i) {
        if (account[i].getType() == authority::root) {
            rootIndex = i;
            break;
        }
    }

    // 2. Load Expressages
    ifstream expFile(expressageFile);
    if (!expFile.is_open()) {
        cerr << "Warning: Could not open expressage file: " << expressageFile << endl;
        return;
    }

    if (getline(expFile, line)) {
        try {
            expressageNum = stoi(line);
        } catch (...) {
            expressageNum = 0;
        }
    }

    expressage.clear();
    for (int i = 0; i < expressageNum; ++i) {
        if (getline(expFile, line)) {
            stringstream ss(line);
            string id, sendUser, receiveUser, assignTime, signTime, remark, statusStr;
            int status;
            
            // Format: Logistics ID Sender Username Recipient Username Shipment Date Delivery Date Logistics Status Logistics Remark
            ss >> id >> sendUser >> receiveUser >> assignTime >> signTime >> status >> remark;
            
            bool flag = (status == 1); // Flag = true if delivered (status 1)
            ExpressageNode node(id, sendUser, receiveUser, assignTime, signTime, remark, flag);
            expressage.push_back(node);
        }
    }
    expFile.close();
}

// Save: Writes current state to files
void LogisticSys::save(std::string accountFile, std::string expressageFile) {
    // 1. Save Accounts
    ofstream accFile(accountFile);
    if (!accFile.is_open()) {
        cerr << "Error: Could not open account file for writing: " << accountFile << endl;
        return;
    }

    accFile << accountNum << "\n";
    for (const auto& node : account) {
        accFile << node.getId() << " "
                << node.getPassword() << " "
                << node.getName() << " "
                << node.getPhone() << " "
                << fixed << setprecision(2) << node.getMoney() << " "
                << node.getAddress() << " "
                << node.getType() << "\n";
    }
    accFile.close();

    // 2. Save Expressages
    ofstream expFile(expressageFile);
    if (!expFile.is_open()) {
        cerr << "Error: Could not open expressage file for writing: " << expressageFile << endl;
        return;
    }

    expFile << expressageNum << "\n";
    for (const auto& node : expressage) {
        // Format: Logistics ID Sender Username Recipient Username Shipment Date Delivery Date Logistics Status Logistics Remark
        string status_str = node.isDelivered() ? "1" : "0";
        string sign_time_str = node.getSignTime().empty() ? "NULL" : node.getSignTime();
        
        expFile << node.getId() << " "
                << node.getSendUser() << " "
                << node.getReceiveUser() << " "
                << node.getAssignTime() << " "
                << sign_time_str << " "
                << status_str << " "
                << node.getRemark() << "\n";
    }
    expFile.close();
}
