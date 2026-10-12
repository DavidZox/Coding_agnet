#include "common.h"
#include "people_management.h"
#include "utils.h"
#include <iostream>
#include <vector>
#include <string>
#include <map>

int main(int argc, char* argv[]) {
    if (argc < 2) {
        return FAILURE;
    }

    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    std::string command = args[0];
    std::string subcommand = "";
    std::string target = "";
    std::vector<std::string> remaining_args;

    // Parse command structure: ./UMM <command> [target] [options...]
    // or ./UMM <command> <subcommand> [options...]
    if (command == "mentor") {
        if (args.size() < 2) return FAILURE;
        subcommand = "mentor";
        target = args[1]; // target becomes 'assign' or 'lookup'
        for (size_t i = 2; i < args.size(); ++i) {
            remaining_args.push_back(args[i]);
        }
    } else {
        if (args.size() < 2) return FAILURE;
        target = args[1];
        // Check if target is valid (person or school)
        if (!validate_options(command, target)) {
            return FAILURE;
        }
        for (size_t i = 2; i < args.size(); ++i) {
            remaining_args.push_back(args[i]);
        }
        // For non-mentor commands, the subcommand is the command itself
        subcommand = command;
    }

    // Validate if the command and target are allowed
    // Note: for mentor, target is "mentor", which is handled inside handle_options
    if (command != "mentor" && !validate_options(command, target)) {
        return FAILURE;
    }

    std::map<std::string, std::string> options = build_options(remaining_args);

    PeopleManagement pm;
    int result = handle_options(subcommand, target, options, pm);

    return result;
}
