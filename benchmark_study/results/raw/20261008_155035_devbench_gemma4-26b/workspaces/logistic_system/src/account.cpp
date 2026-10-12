#include "account.h"
#include <iomanip>

AccountNode::AccountNode() 
    : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(authority::user) {}

AccountNode::AccountNode(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad, authority _t)
    : id(_id), password(_pwd), name(_nm), phone(_ph), money(_m), address(_ad), type(_t) {}

std::ostream& operator<<(std::ostream& out, AccountNode& a) {
    out << "AccountId: " << a.id << "\n";
    out << "UserName: " << a.name << "\n";
    out << "UserPhone: " << a.phone << "\n";
    out << "Money: " << std::fixed << std::setprecision(2) << a.money << "\n";
    out << "Address: " << a.address << "\n";
    
    out << "UserType: ";
    if (a.type == authority::root) {
        out << "root";
    } else if (a.type == authority::admin) {
        out << "admin";
    } else {
        out << "normal user";
    }
    out << std::endl;
    return out;
}
