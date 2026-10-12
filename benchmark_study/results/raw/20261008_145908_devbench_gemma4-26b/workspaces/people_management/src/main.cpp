#include "common.h"
#include "people_management.h"
#include "utils.h"
#include <iostream>
#include <vector>
#include <string>
#include <map>

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: ./UMM command target [options..]" << std::endl;
        return SUCCESS;
    }

    std::string subcommand = argv[1];
    std::string target = argv[2];

    // Validate subcommand and target
    // Note: For 'mentor', the target is 'assign' or 'lookup', 
    // but the PRD usage shows './UMM mentor assign ...' 
    // where 'mentor' is the command and 'assign'/'lookup' is the target.
    // However, the UML/Architecture suggests handle_options takes subcommand and target.
    if (!validate_options(subcommand, target)) {
        return FAILURE;
    }

    // Build options from remaining arguments
    std::vector<std::string> args;
    for (int i = 3; i < argc; ++i) {
        args.push_back(argv[i]);
    }
    std::map<std::string, std::string> options = build_options(args);

    try {
        PeopleManagement pm;
        int result = handle_options(subcommand, target, options, pm);
        return result;
    } catch (const std::exception& e) {
        std::cerr << "An error occurred: " << e.what() << std::endl;
        return FAILURE;
    } catch (...) {
        std::cerr << "An unknown error occurred." << std::endl;
        return FAILURE;
    }
}
