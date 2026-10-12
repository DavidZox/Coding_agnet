#include <iostream>
#include <string>
#include <vector>
#include <map>
#include "common.h"
#include "utils.h"
#include "people_management.h"

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: ./UMM command target [options..]" << std::endl;
        return NOT_ENOUGH_OPTIONS;
    }

    std::string command = argv[1];
    std::string target = argv[2];

    if (!Utils::contains(commands, command)) {
        std::cerr << "Invalid command: " << command << std::endl;
        return INVALID_OPTION;
    }

    if (!Utils::contains(targets, target)) {
        std::cerr << "Invalid target: " << target << std::endl;
        return INVALID_OPTION;
    }

    std::vector<std::string> args(argv + 3, argv + argc);
    std::map<std::string, std::string> options = build_options(args);

    if (!validate_options(command, target)) {
        std::cerr << "Invalid options for command: " << command << " target: " << target << std::endl;
        return INVALID_OPTION;
    }

    PeopleManagement people_management;
    return handle_options(command, target, options, people_management);
}
