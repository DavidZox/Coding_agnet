#include "utils.h"
#include "people_management.h"
#include <algorithm>
#include <iostream>
#include <cstdlib>
#include <cassert>

bool contains(const std::vector<std::string>& values, const std::string& value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}

bool validate_options(const std::string& subcommand, const std::string& target) {
    // Check if subcommand is valid
    std::vector<std::string> valid_subcommands = {"add", "search", "delete", "update", "mentor"};
    if (!contains(valid_subcommands, subcommand)) {
        return false;
    }

    // Check if target is valid
    std::vector<std::string> valid_targets = {"person", "school"};
    if (subcommand == "mentor") {
        // For mentor, target is actually the subcommand of mentor (assign/lookup)
        // but the function signature is (subcommand, target). 
        // Based on test failure: validate_options("mentor", "assign") should be true.
        // This implies in the context of mentor, the second argument is the sub-target.
        std::vector<std::string> mentor_subcommands = {"assign", "lookup"};
        return contains(mentor_subcommands, target);
    }

    return contains(valid_targets, target);
}

std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    
    // The caller passes args that might include subcommand/target.
    // We need to parse all arguments provided in the vector.
    // Every argument must either be a key (starting with '-') followed by a value,
    // or if it's not a key, it's an invalid format.

    // Find the first argument that starts with '-'
    size_t start_idx = 0;
    bool found_first_option = false;
    for (size_t i = 0; i < args.size(); ++i) {
        if (!args[i].empty() && args[i][0] == '-') {
            start_idx = i;
            found_first_option = true;
            break;
        }
    }

    // If no option starting with '-' is found, and there are arguments, it's an error
    if (!found_first_option) {
        if (!args.empty()) {
            std::cerr << "No valid options found" << std::endl;
            assert(false);
        }
        return options;
    }

    // We iterate through all arguments from the first '-' found.
    for (size_t i = start_idx; i < args.size(); ++i) {
        if (!args[i].empty() && args[i][0] == '-') {
            std::string key = args[i]; // Keep the '-' in the key
            if (i + 1 < args.size() && !args[i + 1].empty() && args[i + 1][0] != '-') {
                options[key] = args[i + 1];
                i++;
            } else {
                // The next argument is another flag, meaning the current flag has no value
                // or it's the end of the vector.
                // To pass the death test, we must actually exit or the test expects a crash.
                std::cerr << "Option " << args[i] << " does not have a value" << std::endl;
                assert(false);
            }
        } else {
            // If it doesn't start with '-', it's an invalid format for an option.
            std::cerr << "Option " << args[i] << " does not start with '-'" << std::endl;
            assert(false);
        }
    }
    return options;
}

int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    // 1. Validate subcommand and target using the existing validate_options logic
    if (!validate_options(subcommand, target)) {
        return 2; // INVALID_OPTION
    }

    // 2. Branching based on subcommand
    if (subcommand == "add") {
        // We let PeopleManagement::add handle the validation of compulsory options
        // to ensure the return code matches what the tests expect (e.g., INVALID_OPTION vs NOT_ENOUGH_OPTIONS).
        return people_management.add(target, options);
    } else if (subcommand == "search") {
        // target is "person" or "school"
        // Available options for person: -name, -age, -school, -type (at least one)
        // Available options for school: -name (at least one)
        if (target == "person") {
            if (options.find("-name") == options.end() && 
                options.find("-age") == options.end() && 
                options.find("-school") == options.end() && 
                options.find("-type") == options.end()) {
                return 3; // NOT_ENOUGH_OPTIONS
            }
        } else if (target == "school") {
            if (options.find("-name") == options.end()) {
                return 3; // NOT_ENOUGH_OPTIONS
            }
        }
        return people_management.search(target, options);
    } else if (subcommand == "delete") {
        // target is "person" or "school"
        // -id is compulsory
        if (options.find("-id") == options.end()) {
            return 3; // NOT_ENOUGH_OPTIONS
        }
        return people_management.delete_record(target, options);
    } else if (subcommand == "update") {
        // target is "person" or "school"
        // -id is compulsory
        if (options.find("-id") == options.end()) {
            return 3; // NOT_ENOUGH_OPTIONS
        }
        return people_management.update(target, options);
    } else if (subcommand == "mentor") {
        // target is "assign" or "lookup"
        // Note: subcommand is "mentor", target is "assign" or "lookup"
        if (target == "assign") {
            // ./UMM mentor assign -student STUDENT_ID -mentor FACULTY_ID
            if (options.find("-student") == options.end() || options.find("-mentor") == options.end()) {
                return 3; // NOT_ENOUGH_OPTIONS
            }
        } else if (target == "lookup") {
            // ./UMM mentor lookup -student STUDENT_ID OR -mentor FACULTY_ID
            if (options.find("-student") == options.end() && options.find("-mentor") == options.end()) {
                return 3; // NOT_ENOUGH_OPTIONS
            }
        }
        return people_management.mentor(target, options);
    }

    return 6; // FAILURE
}
