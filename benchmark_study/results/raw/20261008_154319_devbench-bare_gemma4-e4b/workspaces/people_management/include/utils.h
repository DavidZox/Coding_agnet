#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <vector>
#include <map>

namespace Global {
    /**
     * @brief Checks if a given string exists within a vector of strings.
     * @param values The vector of strings to search within.
     * @param value The string to search for.
     * @return true if the value is found, false otherwise.
     */
    bool contains(const std::vector<std::string>& values, const std::string& value);

    /**
     * @brief Validates if the given command line option is valid for the specified subcommand and target.
     * @param subcommand The command (e.g., "add", "search").
     * @param target The entity target (e.g., "person", "school").
     * @return true if the option is valid, false otherwise.
     */
    bool validate_options(const std::string& subcommand, const std::string& target);

    /**
     * @brief Builds a map of options from a vector of command line arguments.
     * @param args The vector of arguments following the command and target.
     * @return A map where keys are option names and values are option values.
     */
    std::map<std::string, std::string> build_options(const std::vector<std::string>& args);

    /**
     * @brief Handles the command line options by directing to the appropriate PeopleManagement function.
     * @param subcommand The command issued by the user.
     * @param target The entity target (person or school).
     * @param options The parsed options map.
     * @param people_management Reference to the PeopleManagement instance.
     * @return An integer status code indicating success or failure.
     */
    int handle_options(const std::string& subcommand, const std::string& target, 
                       const std::map<std::string, std::string>& options, 
                       const class PeopleManagement& people_management);
}

#endif // UTILS_H
