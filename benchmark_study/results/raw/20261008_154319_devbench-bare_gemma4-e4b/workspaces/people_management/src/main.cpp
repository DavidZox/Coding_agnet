#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <cstdlib> // For exit()

#include "common.h"
#include "utils.h"
#include "people_management.h"

/**
 * @brief Main entry point for the University Management System (UMM).
 * 
 * Reads command-line arguments, validates them, initializes PeopleManagement,
 * and directs the operation to the appropriate handler.
 * 
 * @param argc Argument count.
 * @param argv Argument vector.
 * @return int Exit status code.
 */
int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <command> <target> [options...]" << std::endl;
        std::cerr << "Available commands: ";
        for (size_t i = 0; i < commands.size(); ++i) {
            std::cerr << commands[i] << (i == commands.size() - 1 ? "" : ", ");
        }
        std::cerr << std::endl;
        return FAILURE;
    }

    std::string subcommand = argv[1];
    std::string target = (argc > 2) ? argv[2] : "";

    if (subcommand == "mentor" && argc >= 3) {
        // Special handling for mentor command which doesn't strictly follow target structure
        // We treat 'mentor' as the subcommand and the next argument as the action/target
        target = argv[2];
        if (argc < 3) {
             std::cerr << "Error: Mentor command requires an action (assign/lookup)." << std::endl;
             return FAILURE;
        }
    } else if (subcommand != "mentor" && argc < 3) {
        std::cerr << "Error: Command '" << subcommand << "' requires a target (person or school)." << std::endl;
        return FAILURE;
    }

    // 1. Build options map from remaining arguments
    std::vector<std::string> args_for_options;
    if (subcommand == "mentor") {
        // For mentor, arguments start from index 3 (after mentor action)
        for (int i = 3; i < argc; ++i) {
            args_for_options.push_back(argv[i]);
        }
    } else {
        // For other commands, arguments start from index 3 (after command and target)
        for (int i = 3; i < argc; ++i) {
            args_for_options.push_back(argv[i]);
        }
    }

    std::map<std::string, std::string> options = Global::build_options(args_for_options);

    // 2. Validate options
    if (!Global::validate_options(subcommand, target)) {
        std::cerr << "Error: Invalid options provided for command '" << subcommand << "' and target '" << target << "'." << std::endl;
        return INVALID_OPTION;
    }

    // 3. Initialize PeopleManagement
    PeopleManagement pm(db_name);

    // 4. Handle options and execute command
    int status = Global::handle_options(subcommand, target, options, pm);

    if (status != SUCCESS) {
        std::cerr << "Operation failed with status code: " << status << std::endl;
    }

    return status;
}
