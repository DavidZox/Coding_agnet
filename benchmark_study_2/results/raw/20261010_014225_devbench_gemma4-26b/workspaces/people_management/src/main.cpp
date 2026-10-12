#include "common.h"
#include "people_management.h"
#include "utils.h"
#include <iostream>
#include <vector>
#include <string>

int main(int argc, char* argv[]) {
    if (argc < 3) {
        // The usage is ./UMM command target [options..]
        // If we don't even have command and target, it's a failure.
        return Global::FAILURE;
    }

    std::string subcommand = argv[1];
    std::string target = argv[2];

    // Validate if the subcommand and target are allowed
    if (!Global::validate_options(subcommand, target)) {
        return Global::INVALID_OPTION;
    }

    // Special case for 'mentor' which has a subcommand structure: mentor assign/lookup
    // Based on PRD: ./UMM mentor assign -student STUDENT_ID -mentor FACULTY_ID
    // In this case, argv[1] is 'mentor', argv[2] is 'assign' or 'lookup'.
    // However, the UML/PRD implies 'mentor' is the command and 'assign'/'lookup' is the target.
    // Let's check if subcommand is 'mentor'.
    
    // According to PRD: ./UMM mentor assign ...
    // Here subcommand = "mentor", target = "assign".
    // But validate_options might expect target to be "person" or "school".
    // Let's handle the 'mentor' command specifically if it's not in the standard person/school targets.
    
    // If the command is 'mentor', the target is the subcommand of mentor (assign/lookup).
    // We need to adjust the logic to pass the correct target to handle_options.
    
    std::string actual_target = target;
    std::vector<std::string> args;
    int start_idx = 3;

    if (subcommand == "mentor") {
        // For mentor, the target is actually the next argument (assign/lookup)
        // and the options follow.
        // Example: ./UMM mentor assign -student 1 -mentor 2
        // argv[1]="mentor", argv[2]="assign", argv[3]="-student", argv[4]="1"...
        if (argc < 4) return Global::NOT_ENOUGH_OPTIONS;
        actual_target = argv[2]; // "assign" or "lookup"
        // We need to shift the arguments so that handle_options sees 'mentor' as subcommand
        // and 'assign' as target.
        // But the signature is handle_options(subcommand, target, options, pm)
        // So we call handle_options("mentor", "assign", options, pm)
        // Wait, the PRD says: ./UMM mentor assign ...
        // This means subcommand="mentor", target="assign".
        // Let's re-read: "subcommand target [options..]"
        // If subcommand is "mentor", target is "assign" or "lookup".
        // This fits the pattern.
    }

    // Collect all options from argv[3] onwards
    for (int i = 3; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    try {
        PeopleManagement pm;
        std::map<std::string, std::string> options = Global::build_options(args);
        
        // If it's a mentor command, the subcommand is 'mentor' and target is 'assign'/'lookup'
        // If it's add/search/delete/update, subcommand is 'add'/'search'/'delete'/'update'
        // and target is 'person'/'school'.
        
        // Let's re-evaluate the command structure from PRD:
        // ./UMM add person ... -> subcommand="add", target="person"
        // ./UMM mentor assign ... -> subcommand="mentor", target="assign"
        
        // The logic in handle_options should handle these.
        // However, the validate_options might fail if target is "assign".
        // Let's check if we need to treat 'mentor' differently.
        
        // If subcommand is mentor, we don't validate target against person/school.
        bool is_mentor = (subcommand == "mentor");
        if (!is_mentor && !Global::validate_options(subcommand, target)) {
            return Global::INVALID_OPTION;
        }

        return Global::handle_options(subcommand, target, options, pm);

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return Global::FAILURE;
    }
}
