#include <iostream>
#include <vector>
#include <string>
#include <map>
#include "people_management.h"
#include "utils.h"
#include "common.h"

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cout << "Usage: ./UMM command target [options..]" << std::endl;
        return Global::SUCCESS;
    }

    std::string command = argv[1];
    std::string target = argv[2];

    // The command structure is: ./UMM command target [options..]
    // or ./UMM mentor [subcommand] [options..]
    
    if (command == "mentor") {
        if (argc < 3) {
            return Global::FAILURE;
        }
        std::string subcommand = argv[2];
        
        // For mentor, the options start from argv[3]
        std::vector<std::string> mentor_args;
        for (int i = 1; i < argc; ++i) {
            mentor_args.push_back(argv[i]);
        }
        std::map<std::string, std::string> options = Global::build_options(mentor_args);
        
        PeopleManagement pm;
        return pm.mentor(subcommand, options);
    } else {
        if (!Global::validate_options(command, target)) {
            return Global::FAILURE;
        }

        // The options start from argv[3]
        std::vector<std::string> options_args;
        for (int i = 1; i < argc; ++i) {
            options_args.push_back(argv[i]);
        }
        std::map<std::string, std::string> options = Global::build_options(options_args);
        
        PeopleManagement pm;
        return Global::handle_options(command, target, options, pm);
    }

    return Global::SUCCESS;
}
