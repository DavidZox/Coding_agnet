#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <string>
#include <vector>
#include <map>
#include <sqlite3.h>
#include "common.h"

class PeopleManagement {
public:
    PeopleManagement();
    ~PeopleManagement();

    void add(const std::string& target, const std::map<std::string, std::string>& options) const;
    void search(const std::string& target, const std::map<std::string, std::string>& options) const;
    void delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;
    void update(const std::string& target, const std::map<std::string, std::string>& options) const;
    void mentor(const std::string& target, const std::map<std::string, std::string>& options) const;

private:
    sqlite3* db;

    void check_select(const std::string sql) const;
    void check_database(const char* db_name) const;
    void execute_sql_from_file(const char* file_name) const;
    static int search_callback(void* data, int argc, char** argv, char** azColName);
};

bool validate_options(const std::string& subcommand, const std::string& target);
std::map<std::string, std::string> build_options(const std::vector<std::string>& args);
int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);

#endif // PEOPLE_MANAGEMENT_H
