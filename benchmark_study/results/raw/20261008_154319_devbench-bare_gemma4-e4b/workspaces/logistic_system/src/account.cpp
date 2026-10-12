#include "account.h"
#include <iostream>
#include <sstream>
#include <iomanip>

// --- AccountNode Implementation ---

AccountNode::AccountNode() : money(0.0), type(user) {}

AccountNode::AccountNode(_id, _pwd, _nm, _ph, _m, _ad, _t)
    : id(_id), password(_pwd), name(_nm), phone(_ph), money(_m), address(_ad), type(_t) {}

std::ostream& operator<<(std::ostream& out, const AccountNode& a) {
    // Format required for account.txt: username password name phone balance address type
    out << a.id << " " << a.password << " " << a.name << " " << a.phone << " "
        << std::fixed << std::setprecision(2) << a.money << " " << a.address << " " << a.type;
    return out;
}
