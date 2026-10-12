#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <string>
#include <map>
#include <vector>
#include <sqlite3.h>
#include "common.h" // Include common.h to access global constants

// Forward declaration of PeopleManagement is needed before Global uses it in handle_options signature
class PeopleManagement;

// Global class interface as per UML diagram
class Global {
public:
    // Status codes
    static const int SUCCESS = 0;
    static const int DB_OPEN_ERROR = 1;
    static const int INVALID_OPTION = 2;
    static const int NOT_ENOUGH_OPTIONS = 3;
    static const int RECORD_NOT_EXISTS = 4;
    static const int SQL_EXECUTION_ERROR = 5;
    static const int FAILURE = 6;

    // Global functions interface
    static bool validate_options(const std::string& subcommand, const std::string& target);
    static std::map<std::string, std::string> build_options(const std::vector<std::string>& args);
    static int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);
    
    // Contains function moved here to resolve namespace conflict and align with UML Global concept
    static bool contains(const std::vector<std::string>& values, const std::string& value);
};

class PeopleManagement {
private:
    sqlite3* db;

    // Private helper methods
    void check_select(const std::string& sql) const;
    bool check_database(const char* db_name) const;
    bool execute_sql_from_file(const char* file_name) const;
    // Modified signature to return int to match sqlite3_exec requirement
    static int search_callback(void *data, int argc, char **argv, char **azColName);

public:
    // Constructor: opens the database
    PeopleManagement();

    // Destructor: closes the database
    ~PeopleManagement();

    // Public methods
    int add(const std::string& target, const std::map<std::string, std::string>& options) const;
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;
};

#endif // PEOPLE_MANAGEMENT_H
