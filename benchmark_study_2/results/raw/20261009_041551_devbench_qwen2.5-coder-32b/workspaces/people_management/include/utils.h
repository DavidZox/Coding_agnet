#ifndef UTILS_H
#define UTILS_H

#include <vector>
#include <string>
#include <map>
#include "common.h"
#include "people_management.h"

bool contains(const std::vector<std::string>& values, const std::string& value);

bool validate_options(const std::string& subcommand, const std::string& target);

int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);

#endif // UTILS_H
