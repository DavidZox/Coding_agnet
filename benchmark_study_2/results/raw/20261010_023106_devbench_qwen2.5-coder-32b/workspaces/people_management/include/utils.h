#ifndef UTILS_H
#define UTILS_H

#include <vector>
#include <string>
#include <map>
// #include "people_management.h"  // Remove this line to avoid circular dependency

namespace utils {
    bool contains(const std::vector<std::string>& values, const std::string& value);

    bool validate_options(const std::string& subcommand, const std::string& target);
    std::map<std::string, std::string> build_options(const std::vector<std::string>& args);
    int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, class PeopleManagement& people_management);
}

#endif // UTILS_H
