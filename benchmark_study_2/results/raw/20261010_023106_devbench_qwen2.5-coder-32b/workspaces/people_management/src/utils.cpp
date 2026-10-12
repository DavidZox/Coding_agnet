#include "utils.h"
#include <algorithm>
#include <iostream>
#include <string>
#include <vector>
#include <map>
#include "common.h"
#include "people_management.h"

bool utils::contains(const std::vector<std::string>& values, const std::string& value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}

bool utils::validate_options(const std::string& subcommand, const std::string& target) {
    if (!utils::contains(commands, subcommand)) {
        return false;
    }
    if (!utils::contains(targets, target)) {
        return false;
    }
    return true;
}

std::map<std::string, std::string> utils::build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i][0] == '-') {
            if (i + 1 < args.size() && args[i + 1][0] != '-') {
                options[args[i].substr(1)] = args[i + 1];
                ++i; // Skip the next argument as it is the value for the current option
            } else {
                options[args[i].substr(1)] = ""; // No value provided for this option
            }
        }
    }
    return options;
}

int utils::handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, PeopleManagement& people_management) {
    if (subcommand == "add") {
        return people_management.add(target, options) ? SUCCESS : FAILURE;
    } else if (subcommand == "search") {
        return people_management.search(target, options) ? SUCCESS : FAILURE;
    } else if (subcommand == "delete") {
        return people_management.delete_record(target, options) ? SUCCESS : FAILURE;
    } else if (subcommand == "update") {
        return people_management.update(target, options) ? SUCCESS : FAILURE;
    } else if (subcommand == "mentor") {
        return people_management.mentor(target, options) ? SUCCESS : FAILURE;
    }
    return INVALID_OPTION;
}
