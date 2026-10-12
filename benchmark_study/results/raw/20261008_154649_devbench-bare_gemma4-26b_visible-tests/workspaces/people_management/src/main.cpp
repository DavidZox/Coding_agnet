#include <iostream>
#include <vector>
#include <string>
#include "common.h"
#include "people_management.h"
#include "utils.h"

/**
 * @brief The main function of the project. It accepts command line options from argv,
 * validates options, creates the PeopleManagement instance and directs to corresponding functions.
 */
int main(int argc, char* argv[]) {
    if (argc < 2) {
        return FAILURE;
    }

    std::string subcommand = argv[1];
    
    // The command structure is: ./UMM command target [options..]
    // or ./UMM mentor subcommand [options..]
    
    if (subcommand == "mentor") {
        if (argc < 3) {
            return FAILURE;
        }
        std::string target = argv[2];
        std::vector<std::string> args;
        for (int i = 3; i < argc; ++i) {
            args.push_back(argv[i]);
        }

        try {
            std::map<std::string, std::string> options = build_options(args);
            PeopleManagement pm;
            return handle_options(subcommand, target, options, pm);
        } catch (const std::exception& e) {
            std::cerr << e.what() << std::endl;
            return FAILURE;
        }
    } else {
        if (argc < 3) {
            return FAILURE;
        }
        std::string target = argv[2];
        std::vector<std::string> args;
        for (int i = 3; i < argc; ++i) {
            args.push_back(argv[i]);
        }

        try {
            std::map<std::string, std::string> options = build_options(args);
            PeopleManagement pm;
            return handle_options(subcommand, target, options, pm);
        } catch (const std::exception& e) {
            std::cerr << e.what() << std::endl;
            return FAILURE;
        }
    }

    return SUCCESS;
}
