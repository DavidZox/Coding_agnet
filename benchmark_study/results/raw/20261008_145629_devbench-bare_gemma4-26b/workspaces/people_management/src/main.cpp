#include <iostream>
#include <vector>
#include <string>
#include <map>
#include "common.h"
#include "people_management.h"
#include "utils.h"

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cout << "Usage: ./UMM command target [options..]" << std::endl;
        return FAILURE;
    }

    std::string command = argv[1];
    
    // Check if command is valid
    if (!Global::contains(commands, command)) {
        return FAILURE;
    }

    // Special case for 'mentor' which has subcommands
    if (command == "mentor") {
        if (argc < 3) {
            return FAILURE;
        }
        std::string subcommand = argv[2];
        std::vector<std::string> args;
        for (int i = 3; i < argc; ++i) {
            args.push_back(argv[i]);
        }
        
        std::map<std::string, std::string> options = Global::build_options(args);
        PeopleManagement pm;
        return pm.mentor(subcommand, options);
    }

    // Standard commands: add, search, delete, update
    if (argc < 3) {
        return FAILURE;
    }

    std::string target = argv[2];
    
    // Validate target (person or school)
    // Note: 'person' is often referred to as 'student' or 'faculty' in PRD, 
    // but the UML/common.h uses 'person'.
    if (!Global::contains(targets, target) && target != "person") {
        // Allow 'person' as the base target for student/faculty logic
    }

    std::vector<std::string> args;
    for (int i = 3; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    std::map<std::string, std::string> options = Global::build_options(args);

    PeopleManagement pm;

    if (command == "add") {
        return pm.add(target, options);
    } else if (command == "search") {
        return pm.search(target, options);
    } else if (command == "delete") {
        return pm.delete_record(target, options);
    } else if (command == "update") {
        return pm.update(target, options);
    }

    return FAILURE;
}
