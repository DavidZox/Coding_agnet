#include <iostream>
#include <vector>
#include <string>
#include <map>
#include "include/common.h"
#include "include/people_management.h"
#include "include/utils.h"

int main(int argc, char* argv[]) {
    if (argc < 2) {
        return Global::FAILURE;
    }

    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    std::string subcommand = args[0];
    std::string target;
    std::vector<std::string> remaining_args;

    // Determine subcommand and target based on command type
    if (subcommand == "mentor") {
        // For mentor, subcommand is 'mentor', target is 'assign' or 'lookup'
        if (args.size() < 2) {
            return Global::FAILURE;
        }
        target = args[1];
        for (size_t i = 2; i < args.size(); ++i) {
            remaining_args.push_back(args[i]);
        }
    } else {
        // For add, search, delete, update, target is 'person' or 'school'
        if (args.size() < 2) {
            return Global::FAILURE;
        }
        target = args[1];
        for (size_t i = 2; i < args.size(); ++i) {
            remaining_args.push_back(args[i]);
        }
    }

    // Validate if the subcommand and target are allowed
    if (!Global::validate_options(subcommand, target)) {
        return Global::INVALID_OPTION;
    }

    // Build options map from remaining arguments
    std::map<std::string, std::string> options = Global::build_options(remaining_args);

    // Initialize PeopleManagement (handles DB connection and schema creation)
    PeopleManagement pm;
    // Note: The UML/Architecture doesn't explicitly mention get_db(), 
    // but we check if the constructor succeeded via the internal state or error handling.
    // Since the requirement says pm handles DB connection, we proceed to handle_options.

    // Dispatch to handle_options which directs to specific PM methods
    int result = Global::handle_options(subcommand, target, options, pm);

    return result;
}
