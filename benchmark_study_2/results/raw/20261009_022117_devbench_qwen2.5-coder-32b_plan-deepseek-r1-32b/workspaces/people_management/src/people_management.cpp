#include "people_management.h"
#include <sqlite3.h>
#include <iostream>
#include <fstream>
#include "common.h"

PeopleManagement::PeopleManagement() {
    if (!check_database(db_name.c_str())) {
        std::cerr << "Failed to open database." << std::endl;
        return;
    }

    if (sqlite3_open(db_name.c_str(), &db) != SQLITE_OK) {
        std::cerr << "Cannot open database: " << sqlite3_errmsg(db) << std::endl;
        db = nullptr;
    } else {
        execute_sql_from_file(people_sql_name.c_str());
        execute_sql_from_file(mentorship_sql_name.c_str());
        execute_sql_from_file(school_sql_name.c_str());
    }
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

bool PeopleManagement::check_database(const char* db_name) const {
    sqlite3* test_db;
    int rc = sqlite3_open(db_name, &test_db);
    if (rc == SQLITE_OK) {
        sqlite3_close(test_db);
        return true;
    }
    return false;
}

bool PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        std::cerr << "Cannot open SQL file: " << file_name << std::endl;
        return false;
    }

    std::string sql((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    char* err_message = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        return false;
    }
    return true;
}

bool PeopleManagement::check_select(const std::string sql) const {
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }
    sqlite3_finalize(stmt);
    return true;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    // Implementation of add function
    return SUCCESS;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    // Implementation of search function
    return SUCCESS;
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    // Implementation of delete_record function
    return SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    // Implementation of update function
    return SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    // Implementation of mentor function
    return SUCCESS;
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    // Implementation of search_callback function
    return 0;
}
