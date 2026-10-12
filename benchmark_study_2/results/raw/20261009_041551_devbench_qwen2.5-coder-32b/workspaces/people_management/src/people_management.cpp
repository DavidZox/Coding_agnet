#include "people_management.h"
#include "utils.h"
#include "common.h"
#include <sqlite3.h>
#include <iostream>
#include <map>
#include <string>

PeopleManagement::PeopleManagement() {
    if (check_database(db_name.c_str())) {
        execute_sql_from_file(people_sql_name.c_str());
        execute_sql_from_file(mentorship_sql_name.c_str());
        execute_sql_from_file(school_sql_name.c_str());
    }
}

PeopleManagement::~PeopleManagement() {
    sqlite3_close(db);
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        if (options.find("name") != options.end() && options.find("age") != options.end() &&
            options.find("school") != options.end() && options.find("type") != options.end()) {
            sql = "INSERT INTO people (name, age, school, type) VALUES ('" + options.at("name") + "', " +
                  options.at("age") + ", " + options.at("school") + ", " + options.at("type") + ");";
        } else {
            return NOT_ENOUGH_OPTIONS;
        }
    } else if (target == "school") {
        if (options.find("name") != options.end()) {
            sql = "INSERT INTO school (name) VALUES ('" + options.at("name") + "');";
        } else {
            return NOT_ENOUGH_OPTIONS;
        }
    } else {
        return INVALID_OPTION;
    }
    char* err_message = 0;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message);
    if (rc != SQLITE_OK) {
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
    char* err_message = 0;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &err_message);
    if (rc != SQLITE_OK) {
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
    char* err_message = 0;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message);
    if (rc != SQLITE_OK) {
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
    bool first = true;
    for (const auto& option : options) {
        if (option.first != "id") {
            if (!first) {
                sql += ", ";
            }
            sql += option.first + " = '" + option.second + "'";
            first = false;
        }
    }
    sql += " WHERE id = " + options.at("id") + ";";
    char* err_message = 0;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (options.find("student") != options.end() && options.find("mentor") != options.end()) {
            std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" + options.at("student") + ", " + options.at("mentor") + ");";
            char* err_message = 0;
            int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_message);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL error: " << err_message << std::endl;
                sqlite3_free(err_message);
                return SQL_EXECUTION_ERROR;
            }
            return SUCCESS;
        } else {
            return NOT_ENOUGH_OPTIONS;
        }
    } else if (target == "lookup") {
        if (options.find("student") != options.end()) {
            std::string sql = "SELECT mentor FROM mentorship WHERE student = " + options.at("student") + ";";
            char* err_message = 0;
            int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &err_message);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL error: " << err_message << std::endl;
                sqlite3_free(err_message);
                return SQL_EXECUTION_ERROR;
            }
            return SUCCESS;
        } else if (options.find("mentor") != options.end()) {
            std::string sql = "SELECT student FROM mentorship WHERE mentor = " + options.at("mentor") + ";";
            char* err_message = 0;
            int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &err_message);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL error: " << err_message << std::endl;
                sqlite3_free(err_message);
                return SQL_EXECUTION_ERROR;
            }
            return SUCCESS;
        } else {
            return NOT_ENOUGH_OPTIONS;
        }
    } else {
        return INVALID_OPTION;
    }
}

bool PeopleManagement::check_database(const char* db_name) const {
    int rc = sqlite3_open(db_name, const_cast<sqlite3**>(&db));
    if (rc != SQLITE_OK) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_close(db);
        return false;
    }
    return true;
}

void PeopleManagement::execute_sql_from_file(const char* file_name) const {
    char* sql = nullptr;
    long length;
    FILE* file = fopen(file_name, "r");
    if (file) {
        fseek(file, 0, SEEK_END);
        length = ftell(file);
        fseek(file, 0, SEEK_SET);
        sql = (char*)malloc(length + 1);
        fread(sql, 1, length, file);
        fclose(file);
        sql[length] = '\0';
    }
    if (sql) {
        char* err_message = 0;
        int rc = sqlite3_exec(db, sql, nullptr, nullptr, &err_message);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL error: " << err_message << std::endl;
            sqlite3_free(err_message);
        }
        free(sql);
    }
}

int PeopleManagement::search_callback(void* data, int argc, char** argv, char** azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << " = " << (argv[i] ? argv[i] : "NULL") << std::endl;
    }
    std::cout << std::endl;
    return 0;
}
