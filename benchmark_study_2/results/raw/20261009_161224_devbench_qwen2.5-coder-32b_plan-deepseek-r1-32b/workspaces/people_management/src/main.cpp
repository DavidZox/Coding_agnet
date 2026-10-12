#include <iostream>
#include <vector>
#include <string>
#include <map>
#include "people_management.h"
#include "utils.h"
#include "common.h"

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: ./UMM command target [options..]" << std::endl;
        return NOT_ENOUGH_OPTIONS;
    }

    std::string command = argv[1];
    std::string target = argv[2];

    std::vector<std::string> args(argv + 3, argv + argc);
    std::map<std::string, std::string> options = build_options(args);

    if (!validate_options(command, target)) {
        std::cerr << "Invalid options provided." << std::endl;
        return INVALID_OPTION;
    }

    PeopleManagement people_management;
    return handle_options(command, target, options, people_management);
}
