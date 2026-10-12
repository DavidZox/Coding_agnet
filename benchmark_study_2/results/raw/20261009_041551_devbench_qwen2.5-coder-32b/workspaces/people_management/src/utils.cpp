#include "utils.h"
#include <algorithm> // Include this header for std::find
#include <map> // Include this header for std::map

bool contains(const std::vector<std::string>& values, const std::string& value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}

std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i].substr(0, 2) == "--") {
            std::string key = args[i].substr(2);
            if (i + 1 < args.size() && args[i + 1].substr(0, 2) != "--") {
                options[key] = args[i + 1];
                ++i; // Skip the next argument as it is the value for this option
            } else {
                options[key] = ""; // No value provided for this option
            }
        }
    }
    return options;
}

bool validate_options(const std::string& subcommand, const std::string& target) {
    if (subcommand == "add" || subcommand == "search" || subcommand == "delete" || subcommand == "update" || subcommand == "mentor") {
        if (target == "person" || target == "school") {
            return true;
        }
    }
    return false;
}

int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    if (!validate_options(subcommand, target)) {
        return INVALID_OPTION;
    }

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
    } else {
        return INVALID_OPTION;
    }
}
