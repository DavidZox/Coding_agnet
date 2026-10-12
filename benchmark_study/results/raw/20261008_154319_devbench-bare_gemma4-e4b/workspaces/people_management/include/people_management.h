#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <string>
#include <vector>
#include <map>
#include <sqlite3.h>
#include "common.h"

/**
 * @brief Manages database operations for People, Mentorship, and School entities.
 * Implements the core logic for CRUD and mentorship operations.
 */
class PeopleManagement {
private:
    sqlite3* db;

    /**
     * @brief Internal helper to check the result of an SQL execution.
     * @param sql The SQL statement executed.
     * @return true if execution was successful, false otherwise.
     */
    bool check_select(const std::string& sql) const;

    /**
     * @brief Initializes the database connection and creates necessary tables if they don't exist.
     * @param db_name The name of the SQLite database file.
     * @return true if the database connection and schema setup were successful, false otherwise.
     */
    bool check_database(const char* db_name) const;

    /**
     * @brief Executes an SQL statement read from a file.
     * @param file_name The path to the SQL schema file.
     * @return true if the execution was successful, false otherwise.
     */
    bool execute_sql_from_file(const char* file_name) const;

    /**
     * @brief Callback function used by sqlite3_exec for SELECT operations.
     * @param data Pointer to user data (not used here).
     * @param argc Argument count.
     * @param argv Array of column values.
     * @param azColName Array of column names.
     */
    static void search_callback(void *data, int argc, char **argv, char **azColName);

public:
    /**
     * @brief Constructor: Opens the database and initializes the schema.
     * @param db_name The name of the database file.
     * @return true if the database connection and schema setup were successful, false otherwise.
     */
    PeopleManagement(const std::string& db_name);

    /**
     * @brief Destructor: Closes the database connection.
     */
    ~PeopleManagement();

    /**
     * @brief Adds a new record to the database (person or school).
     * @param target The entity type ("person" or "school").
     * @param options A map containing the data fields for the new record.
     * @return The status code of the operation (SUCCESS or SQL_EXECUTION_ERROR).
     */
    int add(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Searches for records based on provided options.
     * @param target The entity type ("person" or "school").
     * @param options A map containing search criteria (e.g., name, age).
     * @return The status code of the operation (SUCCESS or SQL_EXECUTION_ERROR).
     */
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Deletes a record based on its ID.
     * @param target The entity type ("person" or "school").
     * @param options A map containing the ID to delete (must contain "-id").
     * @return The status code of the operation (SUCCESS or RECORD_NOT_EXISTS).
     */
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Updates an existing record based on its ID and provided options.
     * @param target The entity type ("person" or "school").
     * @param options A map containing the ID and fields to update.
     * @return The status code of the operation (SUCCESS or RECORD_NOT_EXISTS).
     */
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Handles mentorship operations (assign or lookup).
     * @param target The mentorship action ("assign" or "lookup").
     * @param options A map containing necessary IDs (e.g., -student, -mentor).
     * @return The status code of the operation (SUCCESS or SQL_EXECUTION_ERROR).
     */
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;
};

#endif // PEOPLE_MANAGEMENT_H
