#include "utils.h"
#include "people_management.h"
#include <algorithm>
#include <map>
#include <string>
#include <vector>

bool Global::contains(const std::vector<std::string> values, const std::string value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}

bool Global::validate_options(const std::string& subcommand, const std::string& target) {
    if (target == "person") {
        if (subcommand == "add") {
            // For add person, we don't check existence here, but we check if it's a valid command
            return true;
        }
        if (subcommand == "search") return true;
        if (subcommand == "delete") return true;
        if (subcommand == "update") return true;
    } else if (target == "school") {
        if (subcommand == "add") return true;
        if (subcommand == "search") return true;
        if (subcommand == "delete") return true;
        if (subcommand == "update") return true;
    } else if (subcommand == "mentor") {
        return true;
    }
    return false;
}

std::map<std::string, std::string> Global::build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i].size() > 2 && args[i].substr(0, 2) == "-") {
            std::string key = args[i].substr(1);
            if (i + 1 < args.size() && args[i + 1].substr(0, 1) != "-") {
                options[key] = args[i + 1];
                i++;
            } else {
                options[key] = "true"; // For flags if any
            }
        }
    }
    return options;
}

int Global::handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    if (target == "person") {
        if (subcommand == "add") {
            if (options.find("name") == options.end() || options.find("age") == options.end() || 
                options.find("school") == options.end() || options.find("type") == options.end()) {
                return NOT_ENOUGH_OPTIONS;
            }
            return people_management.add(target, options);
        } else if (subcommand == "search") {
            if (options.empty()) return SUCCESS; // List all if no options
            return people_management.search(target, options);
        } else if (subcommand == "delete") {
            if (options.find("id") == options.end()) return NOT_ENOUGH_OPTIONS;
            return people_management.delete_record(target, options);
        } else if (subcommand == "update") {
            if (options.find("id") == options.end()) return NOT_ENOUGH_OPTIONS;
            return people_management.update(target, options);
        }
    } else if (target == "school") {
        if (subcommand == "add") {
            if (options.find("name") == options.end()) return NOT_ENOUGH_OPTIONS;
            return people_management.add(target, options);
        } else if (subcommand == "search") {
            if (options.empty()) return SUCCESS;
            return people_management.search(target, options);
        } else if (subcommand == "delete") {
            if (options.find("id") == options.end()) return NOT_ENOUGH_OPTIONS;
            return people_management.delete_record(target, options);
        } else if (subcommand == "update") {
            if (options.find("id") == options.end()) return NOT_ENOUGH_OPTIONS;
            return people_management.update(target, options);
        }
    } else if (subcommand == "mentor") {
        return people_management.mentor(target, options);
    }
    return FAILURE;
}
