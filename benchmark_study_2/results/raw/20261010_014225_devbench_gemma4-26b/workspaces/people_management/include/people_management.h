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

    int add(const std::string& target, const std::map<std::string, std::string>& options) const;
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;

private:
    sqlite3* db;

    int check_select(const std::string sql) const;
    int check_database(const std::string& db_name);
    int execute_sql_from_file(const std::string& file_name);
    static int search_callback(void* data, int argc, char** argv, char** azColName);
};

#endif // PEOPLE_MANAGEMENT_H
