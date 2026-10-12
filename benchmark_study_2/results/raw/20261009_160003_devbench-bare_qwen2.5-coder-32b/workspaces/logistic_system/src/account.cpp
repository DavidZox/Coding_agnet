#include "account.h"

AccountNode::AccountNode() : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(authority::user) {}

AccountNode::AccountNode(const std::string& _id, const std::string& _pwd, const std::string& _nm, const std::string& _ph, double _m, const std::string& _ad, authority _t)
    : id(_id), password(_pwd), name(_nm), phone(_ph), money(_m), address(_ad), type(_t) {}

std::ostream& operator<<(std::ostream& out, const AccountNode& a) {
    out << "AccountId: " << a.id << "\n"
        << "UserName: " << a.name << "\n"
        << "UserPhone: " << a.phone << "\n"
        << "Money: " << std::fixed << std::setprecision(2) << a.money << "\n"
        << "Address: " << a.address << "\n"
        << "UserType: ";
    switch (a.type) {
        case authority::root:
            out << "root";
            break;
        case authority::admin:
            out << "admin";
            break;
        case authority::user:
            out << "normal user";
            break;
    }
    out << "\n";
    return out;
}
