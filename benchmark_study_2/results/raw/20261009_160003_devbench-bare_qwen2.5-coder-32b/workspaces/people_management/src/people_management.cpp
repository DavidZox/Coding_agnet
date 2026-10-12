#include <iostream>
#include <string>
#include <map>
#include <vector>
#include <sqlite3.h>
#include "common.h"
#include "people_management.h"

PeopleManagement::PeopleManagement() {
    if (sqlite3_open(db_name.c_str(), &db) != SQLITE_OK) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
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

bool PeopleManagement::check_select(const std::string& sql) const {
    sqlite3_stmt* stmt;
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }
    sqlite3_finalize(stmt);
    return true;
}

bool PeopleManagement::check_database(const char* db_name) const {
    return db != nullptr;
}

bool PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        std::cerr << "Can't open SQL file: " << file_name << std::endl;
        return false;
    }
    std::string sql((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    char* err_message = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message) != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        return false;
    }
    return true;
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << " ";
    }
    std::cout << std::endl;
    return 0;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" + options.at("name") + "', " +
              options.at("age") + ", " + options.at("school") + ", " + options.at("type") + ");";
    } else if (target == "school") {
        sql = "INSERT INTO school (name) VALUES ('" + options.at("name") + "');";
    } else {
        return INVALID_OPTION;
    }

    char* err_message = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message) != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM " + target + " WHERE 1=1";
    for (const auto& option : options) {
        sql += " AND " + option.first + " = '" + option.second + "'";
    }
    sql += ";";

    char* err_message = nullptr;
    if (sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &err_message) != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) {
        return NOT_ENOUGH_OPTIONS;
    }
    std::string sql = "DELETE FROM " + target + " WHERE id = " + options.at("id") + ";";

    char* err_message = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message) != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) {
        return NOT_ENOUGH_OPTIONS;
    }
    std::string sql = "UPDATE " + target + " SET ";
    for (const auto& option : options) {
        if (option.first != "id") {
            sql += option.first + " = '" + option.second + "', ";
        }
    }
    sql.pop_back(); // Remove the last comma
    sql.pop_back(); // Remove the last space
    sql += " WHERE id = " + options.at("id") + ";";

    char* err_message = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message) != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (options.find("student") == options.end() || options.find("mentor") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" + options.at("student") + ", " + options.at("mentor") + ");";
        char* err_message = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message) != SQLITE_OK) {
            std::cerr << "SQL error: " << err_message << std::endl;
            sqlite3_free(err_message);
            return SQL_EXECUTION_ERROR;
        }
        return SUCCESS;
    } else if (target == "lookup") {
        std::string sql;
        if (options.find("student") != options.end()) {
            sql = "SELECT * FROM mentorship WHERE student = " + options.at("student") + ";";
        } else if (options.find("mentor") != options.end()) {
            sql = "SELECT * FROM mentorship WHERE mentor = " + options.at("mentor") + ";";
        } else {
            return NOT_ENOUGH_OPTIONS;
        }
        char* err_message = nullptr;
        if (sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &err_message) != SQLITE_OK) {
            std::cerr << "SQL error: " << err_message << std::endl;
            sqlite3_free(err_message);
            return SQL_EXECUTION_ERROR;
        }
        return SUCCESS;
    } else {
        return INVALID_OPTION;
    }
}
