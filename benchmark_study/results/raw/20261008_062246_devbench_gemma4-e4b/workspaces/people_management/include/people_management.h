#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <string>
#include <map>
#include <vector>
#include <sqlite3.h>
#include <iostream> // Added for potential logging/error reporting in methods
#include <stdexcept> // Added for potential exception handling

// Forward declaration for PeopleManagement to be used in Global functions
class PeopleManagement;

// Global functions declarations (as per UML_class.md)
namespace Global {
    bool contains(const std::vector<std::string>& values, const std::string value);
    bool validate_options(const std::string& subcommand, const std::string& target);
    std::map<std::string, std::string> build_options(const std::vector<std::string>& args);
    int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);

    // Status codes
    const int SUCCESS = 0;
    const int DB_OPEN_ERROR = 1;
    const int INVALID_OPTION = 2;
    const int NOT_ENOUGH_OPTIONS = 3;
    const int RECORD_NOT_EXISTS = 4;
    const int SQL_EXECUTION_ERROR = 5;
    const int FAILURE = 6;
}

/**
 * @brief Manages database operations for People, Mentorship, and School entities.
 */
class PeopleManagement {
private:
    sqlite3* db;

    // Private helper methods
    void check_select(const std::string& sql) const;
    bool check_database(const char* db_name); // Removed const
    void execute_sql_from_file(const char* file_name) const;
    // Note: search_callback must be static as it's a C-style callback function
    static int search_callback(void *data, int argc, char **argv, char **azColName);

public:
    /**
     * @brief Constructor: Opens the database connection and initializes schema.
     */
    PeopleManagement();

    /**
     * @brief Destructor: Closes the database connection.
     */
    ~PeopleManagement();

    /**
     * @brief Adds a record to the database (Person, School, etc.).
     * @param target The entity type (e.g., "person", "school").
     * @param options A map containing the data to add.
     * @return int Status code.
     */
    int add(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Searches for records from the database based on criteria.
     * @param target The entity type (e.g., "person", "school").
     * @param options A map containing search criteria.
     * @return int Status code.
     */
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Deletes a record from the database.
     * @param target The entity type (e.g., "person", "school").
     * @param options A map containing deletion criteria (must include -id).
     * @return int Status code.
     */
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Updates an existing record in the database.
     * @param target The entity type (e.g., "person", "school").
     * @param options A map containing the ID and fields to update.
     * @return int Status code.
     */
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;

    /**
     * @brief Handles mentorship operations (assign/lookup).
     * @param target The mentorship action (e.g., "assign", "lookup").
     * @param options A map containing necessary IDs (student_id, mentor_id).
     * @return int Status code.
     */
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;
};

#endif // PEOPLE_MANAGEMENT_H
