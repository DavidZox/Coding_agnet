#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <sqlite3.h>
#include <map>
#include <string>
#include <vector>

class PeopleManagement {
private:
    sqlite3* db;

    bool check_select(const std::string sql) const;
    bool check_database(const char* db_name) const;
    void execute_sql_from_file(const char* file_name) const;
    static int search_callback(void *data, int argc, char **argv, char **azColName);

public:
    PeopleManagement();
    ~PeopleManagement();
    int add(const std::string& target, const std::map<std::string, std::string>& options) const;
    int search(const std::string& target, const std::map<std::string, std::string>& options) const;
    int delete_record(const std::string& target, const std::map<std::string, std::string>& options) const;
    int update(const std::string& target, const std::map<std::string, std::string>& options) const;
    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;
};

bool validate_options(const std::string& subcommand, const std::string& target);
int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management);

#endif // PEOPLE_MANAGEMENT_H
