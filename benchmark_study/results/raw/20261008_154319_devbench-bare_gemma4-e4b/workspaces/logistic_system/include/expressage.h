#ifndef EXPRESSAGE_H
#define EXPRESSAGE_H

#include <string>
#include <iostream>

// Forward declaration for AccountNode if needed, but based on UML, we might only need string references for now.
// However, since the operator<< is defined in the class, we include iostream.

class ExpressageNode {
private:
    std::string id;
    std::string sendUser;
    std::string receiveUser;
    std::string assignTime;
    std::string signTime;
    std::string remark;
    bool Flag; // Corresponds to Logistics Status (0=not delivered, 1=delivered)

public:
    // Default constructor
    ExpressageNode();

    // Constructor
    ExpressageNode(std::string _id, std::string _sendUser, std::string _receiveUser, std::string _assignTime, std::string _signTime, std::string _remark, bool _Flag);

    /**
     * @brief Signs the expressage with the given time.
     * @param time The time when the expressage is signed.
     * @return True if the expressage is successfully signed, false otherwise.
     */
    bool Sign(std::string time);

    /**
     * @brief Overloaded stream insertion operator for ExpressageNode.
     * @param out The output stream.
     * @param a The ExpressageNode object to be inserted into the stream.
     * @return The output stream after inserting the ExpressageNode object.
     */
    friend std::ostream& operator<<(std::ostream& out, const ExpressageNode& a);
};

#endif // EXPRESSAGE_H
