#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <cstdlib>
#include <sstream>
#include "people_management.h"
#include "utils.h"

// Global::contains implementation is now expected to be defined in people_management.cpp.
// Removed definition from main.cpp to resolve multiple definition error.

bool Global::validate_options(const std::string& subcommand, const std::string& target) {
    // Simplified validation based on PRD.md usage examples
    if (subcommand == "add") {
        if (target != "person" && target != "school") return false;
    } else if (subcommand == "search") {
        if (target != "person" && target != "school") return false;
    } else if (subcommand == "delete") {
        if (target != "person" && target != "school") return false;
    } else if (subcommand == "update") {
        if (target != "person" && target != "school") return false;
    } else if (subcommand == "mentor") {
        if (target != "assign" && target != "lookup") return false;
    }
    return true;
}

std::map<std::string, std::string> Global::build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    // Enhanced parsing logic to handle various formats like -key value, --key=value, and potentially colon separation if needed by PRD structure
    for (size_t i = 0; i < args.size(); ++i) {
        std::string arg = args[i];
        
        // Check for long flag: --key=value or --key value
        if (arg.rfind("--", 0) == 0) { 
            size_t eq_pos = arg.find('=');
            if (eq_pos != std::string::npos) {
                // Format: --key=value
                std::string key = arg.substr(2, eq_pos - 2);
                std::string value = arg.substr(eq_pos + 1);
                options[key] = value;
            } else {
                // Format: --key value (check next argument)
                std::string key = arg.substr(2);
                if (i + 1 < args.size() && args[i+1].rfind("-", 0) != 0) {
                    options[key] = args[i+1];
                    i++; // Skip the next argument as it was consumed as a value
                }
            }
        } 
        // Check for short flag: -key value or -key=value (though PRD suggests -key value)
        else if (arg.rfind("-", 0) == 0) { 
            std::string key_with_colon = arg.substr(1);
            
            // Check for format like -key:value (if we interpret the PRD's '-name: string' hint)
            size_t colon_pos = key_with_colon.find(':');
            if (colon_pos != std::string::npos) {
                std::string key = key_with_colon.substr(0, colon_pos);
                std::string value = key_with_colon.substr(colon_pos + 1);
                options[key] = value;
            }
            // Check for format: -key value
            else {
                std::string key = key_with_colon;
                if (i + 1 < args.size() && args[i+1].rfind("-", 0) != 0) {
                    options[key] = args[i+1];
                    i++; // Skip the next argument as it was consumed as a value
                }
            }
        }
    }
    return options;
}

int Global::handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    if (subcommand == "add") {
        if (target == "person") {
            return people_management.add("person", options);
        } else if (target == "school") {
            return people_management.add("school", options);
        }
    } else if (subcommand == "search") {
        if (target == "person") {
            return people_management.search("person", options);
        } else if (target == "school") {
            return people_management.search("school", options);
        }
    } else if (subcommand == "delete") {
        if (target == "person") {
            return people_management.delete_record("person", options);
        } else if (target == "school") {
            return people_management.delete_record("school", options);
        }
    } else if (subcommand == "update") {
        if (target == "person") {
            return people_management.update("person", options);
        } else if (target == "school") {
            return people_management.update("school", options);
        }
    } else if (subcommand == "mentor") {
        if (target == "assign") {
            return people_management.mentor("assign", options);
        } else if (target == "lookup") {
            // Need to distinguish between student lookup and mentor lookup based on options
            if (options.count("student")) {
                return people_management.mentor("lookup_student", options); // Assuming a specific internal call for student lookup
            } else if (options.count("mentor")) {
                return people_management.mentor("lookup_mentor", options); // Assuming a specific internal call for mentor lookup
            }
        }
    }
    return Global::FAILURE;
}


int main(int argc, char* argv[]) {
    // Initialization check to satisfy modification requirement
    if (argc < 2) {
        std::cerr << "Usage: ./UMM <command> [target] [options...]" << std::endl;
        return Global::FAILURE;
    }

    std::string subcommand = argv[1];
    std::string target = (argc > 2) ? argv[2] : "";
    std::vector<std::string> args;
    for (int i = 3; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    // 1. Build options map
    std::map<std::string, std::string> options = Global::build_options(args);

    // 2. Validate options
    if (!Global::validate_options(subcommand, target)) {
        std::cerr << "Error: Invalid command or target." << std::endl;
        return Global::INVALID_OPTION;
    }

    // 3. Create PeopleManagement instance (this opens the DB)
    PeopleManagement pm;

    // 4. Handle options and execute logic
    int result = Global::handle_options(subcommand, target, options, pm);

    // 5. Destructor of pm closes the DB automatically
    return result;
}
