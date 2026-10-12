#include <iostream>
#include <vector>
#include <string>
#include <map>
#include "common.h"
#include "people_management.h"
#include "utils.h"

int main(int argc, char* argv[]) {
    if (argc < 2) {
        return Global::FAILURE;
    }

    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    std::string command = args[0];
    
    // The first argument is the command (add, search, delete, mentor, update)
    // The second argument is the target (person, school)
    // However, 'mentor' is a special command that might have a subcommand (assign, lookup)
    
    std::string target = "";
    size_t start_idx = 1;

    if (command == "mentor") {
        if (args.size() < 3) {
            return Global::FAILURE;
        }
        target = args[1]; // assign or lookup
        start_idx = 2;
    } else {
        if (args.size() < 2) {
            return Global::FAILURE;
        }
        target = args[1];
        start_idx = 2;
    }

    // Validate command and target
    if (!Global::validate_options(command, target)) {
        return Global::FAILURE;
    }

    // Prepare arguments for handle_options
    // We need to pass the remaining arguments as a vector
    std::vector<std::string> remaining_args;
    for (size_t i = start_idx; i < args.size(); ++i) {
        remaining_args.push_back(args[i]);
    }

    // Create PeopleManagement instance
    PeopleManagement pm;
    
    // We need to adjust handle_options to work with the parsed logic.
    // Based on UML, handle_options takes (subcommand, target, options, people_management)
    // For 'mentor', subcommand is 'assign' or 'lookup'.
    // For others, subcommand is 'add', 'search', etc.
    
    // Re-mapping logic to match Global::handle_options signature:
    // Global::handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management)
    
    std::map<std::string, std::string> options = Global::build_options(remaining_args);

    // If command is mentor, the 'subcommand' in handle_options is actually the first arg after mentor (assign/lookup)
    // If command is add/search/etc, the 'subcommand' is the command itself.
    
    std::string effective_subcommand = command;
    if (command == "mentor") {
        effective_subcommand = target; // target is 'assign' or 'lookup'
        // In this case, the 'target' passed to handle_options should be 'mentor'
        return Global::handle_options(effective_subcommand, "mentor", options, pm);
    } else {
        // For add, search, delete, update, the target is 'person' or 'school'
        // The subcommand is 'add', 'search', etc.
        // But wait, the signature is handle_options(subcommand, target, ...)
        // If command is 'add', target is 'person', then subcommand is 'add'.
        return Global::handle_options(command, target, options, pm);
    }

    return 0;
}
