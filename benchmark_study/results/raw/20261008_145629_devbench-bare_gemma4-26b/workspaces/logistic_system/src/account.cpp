#include "account.h"

AccountNode::AccountNode() 
    : id(""), password(""), name(""), phone(""), money(0.0), address(""), type(authority::user) {}

AccountNode::AccountNode(std::string _id, std::string _pwd, std::string _nm, std::string _ph, 
                         double _m, std::string _ad, authority _t)
    : id(_id), password(_pwd), name(_nm), phone(_ph), money(_m), address(_ad), type(_t) {}

std::ostream& operator<<(std::ostream& out, AccountNode& a) {
    out << a.getId() << " " << a.getPassword() << " " << a.getName() << " "
        << a.getPhone() << " " << a.getMoney() << " " << a.getAddress() << " "
        << static_cast<int>(a.getType());
    return out;
}
