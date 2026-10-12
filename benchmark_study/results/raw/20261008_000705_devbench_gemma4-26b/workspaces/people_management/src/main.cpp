#include <iostream>
#include <vector>
#include <string>
#include <map>
#include "common.h"
#include "people_management.h"
#include "utils.h"

int main(int argc, char* argv[]) {
    if (argc < 2) {
        return Global::SUCCESS;
    }

    std::string subcommand = argv[1];
    std::string target = "";

    // Special handling for 'mentor' command which has a subcommand structure: mentor [assign|lookup]
    if (subcommand == "mentor") {
        if (argc < 3) {
            return Global::FAILURE;
        }
        target = argv[2];
        
        // The actual options start from index 3
        std::vector<std::string> mentor_args;
        for (int i = 3; i < argc; ++i) {
            mentor_args.push_back(argv[i]);
        }

        if (!validate_options(subcommand, target)) {
            return Global::FAILURE;
        }

        PeopleManagement pm;
        std::map<std::string, std::string> options = build_options(mentor_args);
        return handle_options(subcommand, target, options, pm);
    } else {
        // Standard commands: add, search, delete, update
        if (argc < 3) {
            return Global::FAILURE;
        }
        target = argv[2];
        
        // The actual options start from index 3
        std::vector<std::string> cmd_args;
        for (int i = 3; i < argc; ++i) {
            cmd_args.push_back(argv[i]);
        }

        if (!validate_options(subcommand, target)) {
            return Global::FAILURE;
        }

        PeopleManagement pm;
        std::map<std::string, std::string> options = build_options(cmd_args);
        return handle_options(subcommand, target, options, pm);
    }

    return Global::SUCCESS;
}
