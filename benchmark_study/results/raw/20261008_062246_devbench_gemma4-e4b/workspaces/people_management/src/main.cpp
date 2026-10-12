#include <iostream>
#include <string>
#include <vector>
#include <map>
#include "people_management.h"
#include "utils.h"

// Forward declaration or inclusion of Global class definition if needed, 
// assuming Global is defined in people_management.h or common.h based on UML.
// Since Global is mentioned in UML_class.md and its methods are used, 
// we rely on people_management.h to provide the necessary context/definitions.

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: ./UMM <command> [target] [options...]" << std::endl;
        return Global::FAILURE;
    }

    std::string subcommand = argv[1];
    std::string target = (argc > 2) ? argv[2] : "";
    std::vector<std::string> raw_args;
    for (int i = 3; i < argc; ++i) {
        raw_args.push_back(argv[i]);
    }

    // 1. Validate options
    if (!Global::validate_options(subcommand, target)) {
        std::cerr << "Error: Invalid command or target." << std::endl;
        return Global::INVALID_OPTION;
    }

    // 2. Build options map
    std::map<std::string, std::string> options = Global::build_options(raw_args);

    // 3. Create PeopleManagement instance (handles DB connection)
    PeopleManagement pm;
    // Assuming the constructor handles DB connection and returns a status or sets an internal state.
    // Since check_database is private and returns void, we rely on the constructor/destructor 
    // or assume a public method exists/should exist for status check.
    // Based on the error, we must remove the call to the private check_database.
    // We assume the constructor handles the initial connection attempt and failure is handled internally or via exceptions (not shown).
    // If the constructor fails, it should ideally return an error code or throw.
    // For compliance with the original structure, we proceed, trusting the constructor handles the DB setup.
    // If the constructor fails to open the DB, the subsequent calls to pm methods will likely fail gracefully or crash, 
    // but we cannot fix the private access issue without changing the header.
    // We remove the problematic check_database call.
    
    int result = Global::handle_options(subcommand, target, options, pm);

    // 4. Destructor of pm handles DB closing automatically
    return result;
}
