#include "people_management.h"
#include "common.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>

PeopleManagement::PeopleManagement() : db(nullptr) {
    if (check_database(db_name) != SUCCESS) {
        // Error message handled in check_database
    } else {
        execute_sql_from_file(people_sql_name);
        execute_sql_from_file(school_sql_name);
        execute_sql_from_file(mentorship_sql_name);
    }
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

int PeopleManagement::check_database(const char* db_name) {
    int rc = sqlite3_open(db_name, &db);
    if (rc) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        return DB_OPEN_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        return SQL_EXECUTION_ERROR;
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL error in " << file_name << ": " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        if (options.find("-name") == options.end() || options.find("-age") == options.end() ||
            options.find("-school") == options.end() || options.find("-type") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        std::string name = options.at("-name");
        std::string age = options.at("-age");
        std::string school = options.at("-school");
        std::string type = options.at("-type");
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" + name + "', " + age + ", " + school + ", " + type + ");";
    } else if (target == "school") {
        if (options.find("-name") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        std::string name = options.at("-name");
        sql = "INSERT INTO school (name) VALUES ('" + name + "');";
    } else {
        return INVALID_OPTION;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    } else {
        std::cout << "Record added successfully." << std::endl;
        return SUCCESS;
    }
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM " + target;
    std::vector<std::string> conditions;

    if (target == "person") {
        if (options.count("-name")) conditions.push_back("name = '" + options.at("-name") + "'");
        if (options.count("-age")) conditions.push_back("age = " + options.at("-age"));
        if (options.count("-school")) conditions.push_back("school = " + options.at("-school"));
        if (options.count("-type")) conditions.push_back("type = " + options.at("-type"));
    } else if (target == "school") {
        if (options.count("-name")) conditions.push_back("name = '" + options.at("-name") + "'");
    } else {
        return INVALID_OPTION;
    }

    if (!conditions.empty()) {
        sql += " WHERE ";
        for (size_t i = 0; i < conditions.size(); ++i) {
            sql += conditions[i] + (i == conditions.size() - 1 ? "" : " AND ");
        }
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, (void*)this, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) {
        return NOT_ENOUGH_OPTIONS;
    }
    std::string id = options.at("-id");
    std::string sql = "DELETE FROM " + target + " WHERE ID = " + id + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    } else {
        // Check if anything was actually deleted
        if (sqlite3_changes(db) == 0) {
            return RECORD_NOT_EXISTS;
        }
        std::cout << "Record deleted successfully." << std::endl;
        return SUCCESS;
    }
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) {
        return NOT_ENOUGH_OPTIONS;
    }
    std::string id = options.at("-id");
    std::string sql = "UPDATE " + target + " SET ";
    std::vector<std::string> updates;

    if (target == "person") {
        if (options.count("-name")) updates.push_back("name = '" + options.at("-name") + "'");
        if (options.count("-age")) updates.push_back("age = " + options.at("-age"));
        if (options.count("-school")) updates.push_back("school = " + options.at("-school"));
        if (options.count("-type")) updates.push_back("type = " + options.at("-type"));
    } else if (target == "school") {
        if (options.count("-name")) updates.push_back("name = '" + options.at("-name") + "'");
    } else {
        return INVALID_OPTION;
    }

    if (updates.empty()) {
        return INVALID_OPTION;
    }

    for (size_t i = 0; i < updates.size(); ++i) {
        sql += updates[i] + (i == updates.size() - 1 ? "" : ", ");
    }
    sql += " WHERE ID = " + id + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    } else {
        if (sqlite3_changes(db) == 0) {
            return RECORD_NOT_EXISTS;
        }
        std::cout << "Record updated successfully." << std::endl;
        return SUCCESS;
    }
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    // target here is the subcommand: "assign" or "lookup"
    if (target == "assign") {
        if (options.find("-student") == options.end() || options.find("-mentor") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        std::string student = options.at("-student");
        std::string mentor = options.at("-mentor");
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" + student + ", " + mentor + ");";
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return SQL_EXECUTION_ERROR;
        }
        std::cout << "Mentorship assigned." << std::endl;
        return SUCCESS;
    } else if (target == "lookup") {
        std::string sql;
        if (options.count("-student")) {
            if (options.find("-student") == options.end()) return NOT_ENOUGH_OPTIONS;
            sql = "SELECT m.mentor, p.name FROM mentorship m JOIN people p ON m.mentor = p.ID WHERE m.student = " + options.at("-student") + ";";
        } else if (options.count("-mentor")) {
            if (options.find("-mentor") == options.end()) return NOT_ENOUGH_OPTIONS;
            sql = "SELECT p.ID, p.name FROM people p JOIN mentorship m ON p.ID = m.student WHERE m.mentor = " + options.at("-mentor") + ";";
        } else {
            return NOT_ENOUGH_OPTIONS;
        }

        if (!sql.empty()) {
            char* errMsg = nullptr;
            int rc = sqlite3_exec(db, sql.c_str(), search_callback, (void*)this, &errMsg);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL error: " << errMsg << std::endl;
                sqlite3_free(errMsg);
                return SQL_EXECUTION_ERROR;
            }
            return SUCCESS;
        }
        return INVALID_OPTION;
    }
    return INVALID_OPTION;
}

int PeopleManagement::check_select(const std::string sql) const {
    // Placeholder for internal select checks if needed
    return SUCCESS;
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << " ";
    }
    std::cout << std::endl;
    return 0;
}

bool validate_options(const std::string& subcommand, const std::string& target) {
    if (subcommand == "add") {
        if (target == "person") return true;
        if (target == "school") return true;
    } else if (subcommand == "search") {
        if (target == "person") return true;
        if (target == "school") return true;
    } else if (subcommand == "delete") {
        if (target == "person") return true;
        if (target == "school") return true;
    } else if (subcommand == "update") {
        if (target == "person") return true;
        if (target == "school") return true;
    } else if (subcommand == "mentor") {
        if (target == "assign" || target == "lookup") return true;
    }
    return false;
}

std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i].size() > 1 && args[i][0] == '-' && i + 1 < args.size()) {
            options[args[i]] = args[i + 1];
            i++;
        }
    }
    return options;
}

int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    if (subcommand == "add") {
        return people_management.add(target, options);
    } else if (subcommand == "search") {
        return people_management.search(target, options);
    } else if (subcommand == "delete") {
        return people_management.delete_record(target, options);
    } else if (subcommand == "update") {
        return people_management.update(target, options);
    } else if (subcommand == "mentor") {
        return people_management.mentor(target, options);
    }
    return FAILURE;
}
