#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <string>
#include <vector>
#include <map>
#include <sqlite3.h>
#include "common.h"

/**
 * @brief Main class for managing university people, schools, and mentorships.
 */
class PeopleManagement {
public:
    /**
     * @brief Constructor that opens the database.
     */
    PeopleManagement();

    /**
     * @brief Destructor that closes the database.
     */
    ~PeopleManagement();

    /**
     * @brief Add a new record to the database.
     * @param target The table target (e.g., "person", "school").
     * @param options A map of option keys and values.
     * @return SUCCESS on success, or an error code.
     */
    int add(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Search for records in the database.
     * @param target The table target (e.g., "person", "school").
     * @param options A map of search criteria.
     * @return SUCCESS on success, or an error code.
     */
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Delete a record from the database.
     * @param target The table target (e.g., "person", "school").
     * @param options A map containing the "-id" option.
     * @return SUCCESS on success, or an error code.
     */
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Update an existing record in the database.
     * @param target The table target (e.g., "person", "school").
     * @param options A map containing "-id" and the fields to update.
     * @return SUCCESS on success, or an error code.
     */
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Handle mentorship assignments or lookups.
     * @param target The subcommand (e.g., "assign", "lookup").
     * @param options A map of mentorship options.
     * @return SUCCESS on success, or an error code.
     */
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;

private:
    sqlite3* db;

    /**
     * @brief Checks if a SELECT statement returns results.
     * @param sql The SQL query string.
     * @return true if records exist, false otherwise.
     */
    bool check_select(const std::string& sql) const;

    /**
     * @brief Initializes the database by running schema SQL files.
     * @param db_name The name of the database file.
     * @return true if successful, false otherwise.
     */
    bool check_database(const char* db_name) const;

    /**
     * @brief Executes SQL commands from a specified file.
     * @param file_name The path to the .sql file.
     * @return true if successful, false otherwise.
     */
    void execute_sql_from_file(const char* file_name) const;

    /**
     * @brief Callback function for sqlite3_exec to print search results.
     */
    static int search_callback(void* data, int argc, char** argv, char** azColName);
};

namespace Global {
    /**
     * @brief Check if the given command line option is valid.
     */
    bool validate_options(const std::string& subcommand, const std::string& target);

    /**
     * @brief Parse the command line arguments into a map of options.
     */
    std::map<std::string, std::string> build_options(const std::vector<std::string>& args);

    /**
     * @brief Directs the parsed options to the corresponding PeopleManagement function.
     */
    int handle_options(const std::string& subcommand, const std::string& target, 
                       const std::map<std::string, std::string>& options, 
                       const PeopleManagement& people_management);

    // Status codes constants
    const int SUCCESS = 0;
    const int DB_OPEN_ERROR = 1;
    const int INVALID_OPTION = 2;
    const int NOT_ENOUGH_OPTIONS = 3;
    const int RECORD_NOT_EXISTS = 4;
    const int SQL_EXECUTION_ERROR = 5;
    const int FAILURE = 6;
}

#endif // PEOPLE_MANAGEMENT_H
