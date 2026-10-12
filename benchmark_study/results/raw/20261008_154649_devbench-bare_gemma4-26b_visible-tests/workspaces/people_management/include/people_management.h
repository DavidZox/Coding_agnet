#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <sqlite3.h>
#include <string>
#include <vector>
#include <map>
#include "common.h"

/**
 * @brief Main class for managing university people and schools via SQLite.
 */
class PeopleManagement {
public:
    /**
     * @brief Constructor that opens the database and initializes schema.
     */
    PeopleManagement();

    /**
     * @brief Destructor that closes the database connection.
     */
    ~PeopleManagement();

    /**
     * @brief Adds a new record to the database.
     * @param target The table target ("person" or "school").
     * @param options A map of option keys and values.
     * @return Status code.
     */
    int add(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Searches for records in the database.
     * @param target The table target ("person" or "school").
     * @param options A map of search criteria.
     * @return Status code.
     */
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Deletes a record from the database.
     * @param target The table target ("person" or "school").
     * @param options A map containing the "-id" option.
     * @return Status code.
     */
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Updates an existing record in the database.
     * @param target The table target ("person" or "school").
     * @param options A map containing "-id" and fields to update.
     * @return Status code.
     */
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Handles mentorship assignments or lookups.
     * @param target The subcommand ("assign" or "lookup").
     * @param options A map containing mentorship details.
     * @return Status code.
     */
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;

private:
    sqlite3* db;

    /**
     * @brief Checks if a SELECT query returns any results.
     * @param sql The SQL query string.
     * @return true if records exist, false otherwise.
     */
    bool check_select(const std::string sql) const;

    /**
     * @brief Opens the database connection.
     * @param db_name The path to the database file.
     * @return true if successful, false otherwise.
     */
    bool check_database(const char* db_name) const;

    /**
     * @brief Executes SQL commands from a file.
     * @param file_name The path to the .sql file.
     * @return true if successful, false otherwise.
     */
    bool execute_sql_from_file(const char* file_name) const;

    /**
     * @brief Callback function for sqlite3_exec.
     * @param data User data pointer.
     * @param argc Number of columns.
     * @param argv Array of column values.
     * @param azColName Array of column names.
     * @return 0 to continue.
     */
    static int search_callback(void* data, int argc, char** argv, char** azColName);
};

/**
 * @brief Validates if the given subcommand and target are allowed.
 * @param subcommand The command (e.g., "add", "mentor").
 * @param target The entity or subcommand (e.g., "person", "assign").
 * @return true if valid, false otherwise.
 */
bool validate_options(const std::string& subcommand, const std::string& target);

/**
 * @brief Parses command line arguments into a map of options.
 * @param args The vector of command line arguments.
 * @return A map where keys are options (e.g., "-name") and values are their arguments.
 * @throws std::runtime_error for invalid formats.
 */
std::map<std::string, std::string> build_options(const std::vector<std::string>& args);

/**
 * @brief Directs the command to the appropriate PeopleManagement function.
 * @param subcommand The command (e.g., "add", "search").
 * @param target The entity or subcommand (e.g., "person", "assign").
 * @param options The parsed options map.
 * @param people_management Reference to the management instance.
 * @return Status code.
 */
int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);

#endif // PEOPLE_MANAGEMENT_H
