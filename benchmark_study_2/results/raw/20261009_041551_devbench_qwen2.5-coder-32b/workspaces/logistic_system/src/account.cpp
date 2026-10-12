#include "account.h"

AccountNode::AccountNode() : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(authority::user) {}

AccountNode::AccountNode(const std::string& _id, const std::string& _pwd, const std::string& _nm, const std::string& _ph, double _m, const std::string& _ad, authority _t)
    : id(_id), password(_pwd), name(_nm), phone(_ph), money(_m), address(_ad), type(_t) {}

std::ostream& operator<<(std::ostream& out, const AccountNode& a) {
    out << a.id << " " << a.password << " " << a.name << " " << a.phone << " " << a.money << " " << a.address << " ";
    if (a.type == authority::root) {
        out << "0";
    } else if (a.type == authority::admin) {
        out << "1";
    } else {
        out << "2";
    }
    return out;
}
