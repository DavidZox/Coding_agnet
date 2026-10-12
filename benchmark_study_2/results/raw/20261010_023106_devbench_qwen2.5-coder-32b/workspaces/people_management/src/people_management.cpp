#include "people_management.h"
#include "common.h"
#include "utils.h"
#include <sqlite3.h>
#include <iostream>
#include <map>
#include <string>
#include <fstream>

PeopleManagement::PeopleManagement() {
    if (sqlite3_open(db_name.c_str(), &db) != SQLITE_OK) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        db = nullptr;
        throw std::runtime_error("Database open error");
    }
    execute_sql_from_file(people_sql_name.c_str());
    execute_sql_from_file(mentorship_sql_name.c_str());
    execute_sql_from_file(school_sql_name.c_str());
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << " = " << (argv[i] ? argv[i] : "NULL") << std::endl;
    }
    std::cout << std::endl;
    return 0;
}

bool PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql;
    sqlite3_stmt* stmt;
    if (target == "person") {
        sql = "INSERT INTO people (name, age, school, type) VALUES (?, ?, ?, ?);";
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
            std::cerr << "SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
            return false;
        }
        sqlite3_bind_text(stmt, 1, options.at("name").c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 2, std::stoi(options.at("age")));
        sqlite3_bind_int(stmt, 3, std::stoi(options.at("school")));
        sqlite3_bind_int(stmt, 4, std::stoi(options.at("type")));
    } else if (target == "school") {
        sql = "INSERT INTO school (name) VALUES (?);";
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
            std::cerr << "SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
            return false;
        }
        sqlite3_bind_text(stmt, 1, options.at("name").c_str(), -1, SQLITE_STATIC);
    } else {
        std::cerr << "Invalid target" << std::endl;
        return false;
    }
    if (sqlite3_step(stmt) != SQLITE_DONE) {
        std::cerr << "SQL execution error: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_finalize(stmt);
        return false;
    }
    sqlite3_finalize(stmt);
    return true;
}

bool PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql = "SELECT * FROM " + target + " WHERE 1=1";
    sqlite3_stmt* stmt;
    int index = 1;
    for (const auto& option : options) {
        sql += " AND " + option.first + " = ?";
    }
    sql += ";";
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
        std::cerr << "SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }
    for (const auto& option : options) {
        sqlite3_bind_text(stmt, index++, option.second.c_str(), -1, SQLITE_STATIC);
    }
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        for (int i = 0; i < sqlite3_column_count(stmt); i++) {
            std::cout << sqlite3_column_name(stmt, i) << " = " << (sqlite3_column_text(stmt, i) ? (const char*)sqlite3_column_text(stmt, i) : "NULL") << std::endl;
        }
        std::cout << std::endl;
    }
    sqlite3_finalize(stmt);
    return true;
}

bool PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql = "DELETE FROM " + target + " WHERE id = ?;";
    sqlite3_stmt* stmt;
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
        std::cerr << "SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }
    sqlite3_bind_int(stmt, 1, std::stoi(options.at("id")));
    if (sqlite3_step(stmt) != SQLITE_DONE) {
        std::cerr << "SQL execution error: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_finalize(stmt);
        return false;
    }
    sqlite3_finalize(stmt);
    return true;
}

bool PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql = "UPDATE " + target + " SET ";
    sqlite3_stmt* stmt;
    int index = 1;
    for (const auto& option : options) {
        if (option.first != "id") {
            sql += option.first + " = ?, ";
        }
    }
    sql.pop_back();
    sql.pop_back();
    sql += " WHERE id = ?;";
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
        std::cerr << "SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }
    for (const auto& option : options) {
        if (option.first != "id") {
            sqlite3_bind_text(stmt, index++, option.second.c_str(), -1, SQLITE_STATIC);
        }
    }
    sqlite3_bind_int(stmt, index, std::stoi(options.at("id")));
    if (sqlite3_step(stmt) != SQLITE_DONE) {
        std::cerr << "SQL execution error: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_finalize(stmt);
        return false;
    }
    sqlite3_finalize(stmt);
    return true;
}

bool PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql;
    sqlite3_stmt* stmt;
    if (target == "assign") {
        sql = "INSERT INTO mentorship (student, mentor) VALUES (?, ?);";
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
            std::cerr << "SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
            return false;
        }
        sqlite3_bind_int(stmt, 1, std::stoi(options.at("student")));
        sqlite3_bind_int(stmt, 2, std::stoi(options.at("mentor")));
        if (sqlite3_step(stmt) != SQLITE_DONE) {
            std::cerr << "SQL execution error: " << sqlite3_errmsg(db) << std::endl;
            sqlite3_finalize(stmt);
            return false;
        }
    } else if (target == "lookup") {
        sql = "SELECT * FROM mentorship WHERE ";
        if (options.find("student") != options.end()) {
            sql += "student = ?";
        } else if (options.find("mentor") != options.end()) {
            sql += "mentor = ?";
        }
        sql += ";";
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
            std::cerr << "SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
            return false;
        }
        if (options.find("student") != options.end()) {
            sqlite3_bind_int(stmt, 1, std::stoi(options.at("student")));
        } else if (options.find("mentor") != options.end()) {
            sqlite3_bind_int(stmt, 1, std::stoi(options.at("mentor")));
        }
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            for (int i = 0; i < sqlite3_column_count(stmt); i++) {
                std::cout << sqlite3_column_name(stmt, i) << " = " << (sqlite3_column_text(stmt, i) ? (const char*)sqlite3_column_text(stmt, i) : "NULL") << std::endl;
            }
            std::cout << std::endl;
        }
    } else {
        std::cerr << "Invalid target" << std::endl;
        return false;
    }
    sqlite3_finalize(stmt);
    return true;
}

void PeopleManagement::check_select(const std::string sql) const {
    char* err_message = 0;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, 0, &err_message);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        throw std::runtime_error("SQL execution error");
    }
}

void PeopleManagement::check_database(const char* db_name) const {
    sqlite3* temp_db;
    if (sqlite3_open(db_name, &temp_db) != SQLITE_OK) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(temp_db) << std::endl;
        sqlite3_close(temp_db);
        throw std::runtime_error("Database open error");
    }
    sqlite3_close(temp_db);
}

void PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        std::cerr << "Can't open SQL file: " << file_name << std::endl;
        throw std::runtime_error("File open error");
    }
    std::string sql((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    char* err_message = 0;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, 0, &err_message);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << err_message << std::endl;
        sqlite3_free(err_message);
        throw std::runtime_error("SQL execution error");
    }
    file.close();
}
