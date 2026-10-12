#ifndef PEOPLE_MANAGEMENT_H
#define PEOPLE_MANAGEMENT_H

#include <sqlite3.h>
#include <map>
#include <string>

class PeopleManagement {
public:
    PeopleManagement();
    ~PeopleManagement();

    bool add(const std::string& target, const std::map<std::string, std::string>& options);
    bool search(const std::string& target, const std::map<std::string, std::string>& options);
    bool delete_record(const std::string& target, const std::map<std::string, std::string>& options);
    bool update(const std::string& target, const std::map<std::string, std::string>& options);
    bool mentor(const std::string& target, const std::map<std::string, std::string>& options);

private:
    sqlite3* db;
    void check_select(const std::string sql) const;
    void check_database(const char* db_name) const;
    void execute_sql_from_file(const char* file_name) const;
    static int search_callback(void *data, int argc, char **argv, char **azColName);
};

#endif // PEOPLE_MANAGEMENT_H
