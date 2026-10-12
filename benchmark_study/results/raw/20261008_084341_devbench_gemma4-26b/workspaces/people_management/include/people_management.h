#pragma once

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
    sqlite3* db;

    int check_select(const std::string sql) const;
    int check_database(const char* db_name) const;
    int execute_sql_from_file(const char* file_name) const;
    static int search_callback(void* data, int argc, char** argv, char** azColName);
};

namespace Global {
    bool contains(const std::vector<std::string>& values, const std::string& value);
    bool validate_options(const std::string& subcommand, const std::string& target);
    std::map<std::string, std::string> build_options(const std::vector<std::string>& args);
    int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);

    const int SUCCESS = 0;
    const int DB_OPEN_ERROR = 1;
    const int INVALID_OPTION = 2;
    const int NOT_ENOUGH_OPTIONS = 3;
    const int RECORD_NOT_EXISTS = 4;
    const int SQL_EXECUTION_ERROR = 5;
    const int FAILURE = 6;
}
