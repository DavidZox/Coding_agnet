#include <iostream>
#include <vector>
#include <string>
#include <map>
#include "common.h"
#include "people_management.h"
#include "utils.h"

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cout << "Usage: ./UMM command target [options..]" << std::endl;
        return Global::SUCCESS;
    }

    std::string subcommand = argv[1];
    std::string target = argv[2];

    // Check if subcommand is 'mentor' which has its own structure
    // According to PRD: ./UMM mentor assign -student STUDENT_ID -mentor FACULTY_ID
    // In this case, target is 'assign' or 'lookup'
    std::string actual_target = target;
    std::string actual_subcommand = subcommand;

    if (subcommand == "mentor") {
        if (argc < 4) {
            std::cout << "Usage: ./UMM mentor [assign|lookup] [options..]" << std::endl;
            return Global::SUCCESS;
        }
        actual_target = argv[2]; // assign or lookup
        actual_subcommand = "mentor";
    }

    // Validate command and target
    if (!Global::validate_options(actual_subcommand, actual_target)) {
        return Global::FAILURE;
    }

    // Build options from remaining arguments
    std::vector<std::string> args;
    // For both 'mentor' and other commands, options start from argv[3]
    for (int i = 3; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    std::map<std::string, std::string> options = Global::build_options(args);

    try {
        PeopleManagement pm;
        int result = Global::handle_options(actual_subcommand, actual_target, options, pm);

        if (result == Global::SUCCESS) {
            // Success messages are usually handled inside handle_options or the PM methods
            return Global::SUCCESS;
        } else {
            // Error messages are handled inside handle_options
            return result;
        }
    } catch (const std::exception& e) {
        std::cerr << "An error occurred: " << e.what() << std::endl;
        return Global::FAILURE;
    }
}
