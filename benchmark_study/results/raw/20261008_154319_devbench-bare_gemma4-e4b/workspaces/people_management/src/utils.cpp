#include "utils.h"
#include <algorithm>
#include <iostream>

namespace Global {
    /**
     * @brief Checks if a given string exists within a vector of strings.
     * @param values The vector of strings to search within.
     * @param value The string to search for.
     * @return true if the value is found, false otherwise.
     */
    bool contains(const std::vector<std::string>& values, const std::string& value) {
        return std::find(values.begin(), values.end(), value) != values.end();
    }

    /**
     * @brief Validates if the given command line option is valid for the specified subcommand and target.
     * @param subcommand The command (e.g., "add", "search").
     * @param target The entity target (e.g., "person", "school").
     * @return true if the option is valid, false otherwise.
     */
    bool validate_options(const std::string& subcommand, const std::string& target) {
        // This implementation relies on the structure defined in PRD.md and common.h
        // A full validation would be complex, but we check basic structural validity here.
        
        if (subcommand == "add") {
            if (target == "person") {
                // Check if required options for person exist (at least one option must be present if we were to check options map, 
                // but for basic CLI validation, we just ensure the target is valid)
                return true; 
            } else if (target == "school") {
                return true;
            }
        } else if (subcommand == "search") {
            if (target == "person" || target == "school") {
                return true;
            }
        } else if (subcommand == "delete" || subcommand == "update") {
            if (target == "person" || target == "school") {
                return true;
            }
        } else if (subcommand == "mentor") {
            // Mentor command structure is handled specially in main.cpp, here we just validate the action target
            return target == "assign" || target == "lookup";
        }
        
        return false;
    }

    /**
     * @brief Builds a map of options from a vector of command line arguments.
     * @param args The vector of arguments following the command and target.
     * @return A map where keys are option names and values are option values.
     */
    std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
        std::map<std::string, std::string> options;
        for (size_t i = 0; i < args.size(); ++i) {
            const std::string& arg = args[i];
            if (arg.rfind("-", 0) == 0) { // Starts with '-'
                std::string key = arg;
                std::string value = "";
                
                // Check if the next argument exists and is not another flag
                if (i + 1 < args.size() && args[i+1].rfind("-", 0) != 0) {
                    value = args[i+1];
                    i++; // Skip the next argument as it was consumed as a value
                }
                options[key] = value;
            }
        }
        return options;
    }

    /**
     * @brief Handles the command line options by directing to the appropriate PeopleManagement function.
     * @param subcommand The command issued by the user.
     * @param target The entity target (person or school, or action for mentor).
     * @param options The parsed options map.
     * @param people_management Reference to the PeopleManagement instance.
     * @return An integer status code indicating success or failure.
     */
    int handle_options(const std::string& subcommand, const std::string& target, 
                       const std::map<std::string, std::string>& options, 
                       const class PeopleManagement& people_management) {
        
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
            // Target here is the action: "assign" or "lookup"
            if (target == "assign") {
                return people_management.mentor("assign", options);
            } else if (target == "lookup") {
                return people_management.mentor("lookup", options);
            }
        }
        
        return FAILURE;
    }
}
