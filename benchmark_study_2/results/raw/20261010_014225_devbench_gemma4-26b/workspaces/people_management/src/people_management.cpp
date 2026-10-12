#include "people_management.h"
#include "common.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <map>

PeopleManagement::PeopleManagement() : db(nullptr) {
    check_database(db_name);
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

int PeopleManagement::check_database(const std::string& db_name) {
    int rc = sqlite3_open(db_name.c_str(), &db);
    if (rc) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        return Global::DB_OPEN_ERROR;
    }
    execute_sql_from_file(people_sql_name);
    execute_sql_from_file(school_sql_name);
    execute_sql_from_file(mentorship_sql_name);
    return Global::SUCCESS;
}

int PeopleManagement::execute_sql_from_file(const std::string& file_name) {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        return Global::SQL_EXECUTION_ERROR;
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL error from file: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return Global::SQL_EXECUTION_ERROR;
    }
    return Global::SUCCESS;
}

int PeopleManagement::check_select(const std::string sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return Global::SQL_EXECUTION_ERROR;
    }
    return Global::SUCCESS;
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << (i == argc - 1 ? "" : ", ");
    }
    std::cout << std::endl;
    return 0;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        if (options.find("name") == options.end() || options.find("age") == options.end() ||
            options.find("school") == options.end() || options.find("type") == options.end()) {
            return Global::INVALID_OPTION;
        }
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" +
              options.at("name") + "', " + options.at("age") + ", " +
              options.at("school") + ", " + options.at("type") + ");";
    } else if (target == "school") {
        if (options.find("name") == options.end()) {
            return Global::INVALID_OPTION;
        }
        sql = "INSERT INTO school (name) VALUES ('" + options.at("name") + "');";
    } else {
        return Global::FAILURE;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Add error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record added successfully." << std::endl;
    return Global::SUCCESS;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM " + target;
    if (!options.empty()) {
        sql += " WHERE ";
        bool first = true;
        for (auto const& [key, val] : options) {
            if (!first) sql += " AND ";
            if (key == "name") sql += "name = '" + val + "'";
            else if (key == "age") sql += "age = " + val;
            else if (key == "school") sql += "school = " + val;
            else if (key == "type") sql += "type = " + val;
            else sql += "1=1"; // ignore unknown
            first = false;
        }
    }
    return check_select(sql);
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) return Global::NOT_ENOUGH_OPTIONS;
    std::string sql = "DELETE FROM " + target + " WHERE ID = " + options.at("id") + ";";
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Delete error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record deleted." << std::endl;
    return Global::SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) return Global::NOT_ENOUGH_OPTIONS;
    if (options.size() <= 1) return Global::NOT_ENOUGH_OPTIONS;

    std::string sql = "UPDATE " + target + " SET ";
    bool first = true;
    for (auto const& [key, val] : options) {
        if (key == "id") continue;
        if (!first) sql += ", ";
        if (key == "name") sql += "name = '" + val + "'";
        else if (key == "age") sql += "age = " + val;
        else if (key == "school") sql += "school = " + val;
        else if (key == "type") sql += "type = " + val;
        else continue;
        first = false;
    }
    sql += " WHERE ID = " + options.at("id") + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Update error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record updated." << std::endl;
    return Global::SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (options.find("student") == options.end() || options.find("mentor") == options.end()) {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" +
                          options.at("student") + ", " + options.at("mentor") + ");";
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            std::cerr << "Mentor assign error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return Global::SQL_EXECUTION_ERROR;
        }
        std::cout << "Mentorship assigned." << std::endl;
        return Global::SUCCESS;
    } else if (target == "lookup") {
        std::string sql;
        if (options.find("student") != options.end()) {
            sql = "SELECT m.mentor, p.name FROM mentorship m JOIN people p ON m.mentor = p.ID WHERE m.student = " + options.at("student") + ";";
        } else if (options.find("mentor") != options.end()) {
            sql = "SELECT p.name, p.ID FROM mentorship m JOIN people p ON m.student = p.ID WHERE m.mentor = " + options.at("mentor") + ";";
        } else {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        return check_select(sql);
    }
    return Global::FAILURE;
}
