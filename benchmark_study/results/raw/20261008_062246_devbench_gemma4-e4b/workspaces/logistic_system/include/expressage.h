#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include <string>
#include <iostream>
#include <vector> // Included for completeness, though not strictly used in the class definition itself

// Forward declaration for authority, as it's used in AccountNode, 
// and ExpressageNode might interact with it indirectly or for consistency.
// Since we are only implementing ExpressageNode now, we rely on the structure.
// If authority was needed here, we would include account.h.

class ExpressageNode {
private:
    std::string id;
    std::string sendUser;
    std::string receiveUser;
    std::string assignTime;
    std::string signTime;
    std::string remark;
    bool Flag; // 0 for not delivered, 1 for delivered (as per PRD.md)

public:
    // Default constructor
    ExpressageNode();

    // Parameterized constructor
    ExpressageNode(std::string id, std::string sendUser, std::string receiveUser, std::string assignTime, std::string signTime, std::string remark, bool flag);

    // Sign method
    bool Sign(std::string time);

    // Friend declaration for stream insertion operator
    friend std::ostream& operator<<(std::ostream& os, const ExpressageNode& node);

    // Getters added to satisfy external dependencies (src/logistics.cpp)
    const std::string& getId() const { return id; }
    const std::string& getSendUser() const { return sendUser; }
    const std::string& getReceiveUser() const { return receiveUser; }
    const std::string& getAssignTime() const { return assignTime; }
    const std::string& getSignTime() const { return signTime; }
    const std::string& getRemark() const { return remark; }
    bool isDelivered() const { return Flag; }
};

#endif // EXPRESSAGE_H
