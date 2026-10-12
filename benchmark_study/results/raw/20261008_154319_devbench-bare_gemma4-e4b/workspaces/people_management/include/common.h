#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>
#include <sqlite3.h>

// --- Constants ---

// Database Scheme File Paths
const std::string people_sql_name = "sql/people.sql";
const std::string mentorship_sql_name = "sql/mentorship.sql";
const std::string school_sql_name = "sql/school.sql";

// Database Path
const std::string db_name = "university_management.db";

// Command Targets
const std::vector<std::string> commands = {"add", "search", "delete", "mentor", "update"};
const std::vector<std::string> targets = {"person", "school"};

// Status Codes (from Global class in UML)
const int SUCCESS = 0;
const int DB_OPEN_ERROR = 1;
const int INVALID_OPTION = 2;
const int NOT_ENOUGH_OPTIONS = 3;
const int RECORD_NOT_EXISTS = 4;
const int SQL_EXECUTION_ERROR = 5;
const int FAILURE = 6;

// --- Global Functions Declarations (as per UML) ---

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

// Forward declaration of PeopleManagement class
class PeopleManagement;

#endif // COMMON_H
