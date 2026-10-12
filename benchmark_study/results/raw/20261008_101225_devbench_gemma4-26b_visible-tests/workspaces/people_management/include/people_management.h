#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <string>
#include <vector>
#include <map>
#include <sqlite3.h>
#include "common.h"
#include "utils.h"

class PeopleManagement {
public:
    PeopleManagement();
    ~PeopleManagement();

    int add(const std::string& target, const std::map<std::string, std::string>& options) const;
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;

private:
    mutable sqlite3* db;

    void check_select(const std::string sql) const;
    void check_database(const char* db_name) const;
    void execute_sql_from_file(const char* file_name) const;
    static int search_callback(void *data, int argc, char **argv, char **azColName);
};

// Global functions and constants moved to global scope to match test expectations
bool validate_options(const std::string& subcommand, const std::string& target);

std::map<std::string, std::string> build_options(const std::vector<std::string>& args);

int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);

// To maintain compatibility with code that might explicitly use Global::SUCCESS
namespace Global {
    using ::validate_options;
    using ::build_options;
    using ::handle_options;
    
    const int SUCCESS = ::SUCCESS;
    const int DB_OPEN_ERROR = ::DB_OPEN_ERROR;
    const int INVALID_OPTION = ::INVALID_OPTION;
    const int NOT_ENOUGH_OPTIONS = ::NOT_ENOUGH_OPTIONS;
    const int RECORD_NOT_EXISTS = ::RECORD_NOT_EXISTS;
    const int SQL_EXECUTION_ERROR = ::SQL_EXECUTION_ERROR;
    const int FAILURE = ::FAILURE;
}

#endif // PEOPLE_MANAGEMENT_H
