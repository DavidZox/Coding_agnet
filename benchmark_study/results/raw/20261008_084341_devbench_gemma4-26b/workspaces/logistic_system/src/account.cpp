#include "account.h"

AccountNode::AccountNode() 
    : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(user) {}

AccountNode::AccountNode(std::string _id, std::string _pwd, std::string _nm, std::string _ph, double _m, std::string _ad, authority _t)
    : id(_id), password(_pwd), name(_nm), phone(_ph), money(_m), address(_ad), type(_t) {}

std::ostream& operator<<(std::ostream& out, const AccountNode& a) {
    out << a.id << " " << a.password << " " << a.name << " " << a.phone << " " 
        << a.money << " " << a.address << " " << static_cast<int>(a.type);
    return out;
}
