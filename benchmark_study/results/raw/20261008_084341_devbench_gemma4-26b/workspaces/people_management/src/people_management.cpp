#include "people_management.h"
#include "common.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <map>
#include <sqlite3.h>

PeopleManagement::PeopleManagement() : db(nullptr) {
    if (check_database(db_name) != Global::SUCCESS) {
        if (sqlite3_open(db_name, &db) == SQLITE_OK) {
            execute_sql_from_file(people_sql_name);
            execute_sql_from_file(school_sql_name);
            execute_sql_from_file(mentorship_sql_name);
        }
    }
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

int PeopleManagement::check_database(const char* db_name) const {
    std::ifstream f(db_name);
    return f.good() ? Global::SUCCESS : Global::FAILURE;
}

int PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) return Global::FAILURE;

    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    return Global::SUCCESS;
}

int PeopleManagement::check_select(const std::string sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    return Global::SUCCESS;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        if (options.find("name") == options.end() || options.find("age") == options.end() ||
            options.find("school") == options.end() || options.find("type") == options.end()) {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" +
              options.at("name") + "', " + options.at("age") + ", " +
              options.at("school") + ", " + options.at("type") + ");";
    } else if (target == "school") {
        if (options.find("name") == options.end()) {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        sql = "INSERT INTO school (name) VALUES ('" + options.at("name") + "');";
    } else {
        return Global::FAILURE;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record added successfully." << std::endl;
    return Global::SUCCESS;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM " + target + " WHERE 1=1";
    if (target == "person") {
        if (options.count("name")) sql += " AND name LIKE '%" + options.at("name") + "%'";
        if (options.count("age")) sql += " AND age = " + options.at("age");
        if (options.count("school")) sql += " AND school = " + options.at("school");
        if (options.count("type")) sql += " AND type = " + options.at("type");
    } else if (target == "school") {
        if (options.count("name")) sql += " AND name LIKE '%" + options.at("name") + "%'";
    }

    return check_select(sql);
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) return Global::NOT_ENOUGH_OPTIONS;
    
    std::string sql = "DELETE FROM " + target + " WHERE ID = " + options.at("id") + ";";
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record deleted successfully." << std::endl;
    return Global::SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) return Global::NOT_ENOUGH_OPTIONS;
    if (options.size() == 1) return Global::NOT_ENOUGH_OPTIONS;

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
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record updated successfully." << std::endl;
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
            sqlite3_free(errMsg);
            return Global::SQL_EXECUTION_ERROR;
        }
        std::cout << "Mentorship assigned successfully." << std::endl;
        return Global::SUCCESS;
    } else if (target == "lookup") {
        std::string sql;
        if (options.count("student")) {
            sql = "SELECT m.mentor, p.name FROM mentorship m JOIN people p ON m.mentor = p.ID WHERE m.student = " + options.at("student") + ";";
        } else if (options.count("mentor")) {
            sql = "SELECT m.student, p.name FROM mentorship m JOIN people p ON m.student = p.ID WHERE m.mentor = " + options.at("mentor") + ";";
        } else {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        return check_select(sql);
    }
    return Global::FAILURE;
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << (i == argc - 1 ? "" : ", ");
    }
    std::cout << std::endl;
    return 0;
}

// Global functions implementation
bool Global::validate_options(const std::string& subcommand, const std::string& target) {
    if (subcommand == "add") {
        return (target == "person" || target == "school");
    } else if (subcommand == "search") {
        return (target == "person" || target == "school");
    } else if (subcommand == "delete") {
        return (target == "person" || target == "school");
    } else if (subcommand == "update") {
        return (target == "person" || target == "school");
    } else if (subcommand == "mentor") {
        return (target == "assign" || target == "lookup");
    }
    return false;
}

std::map<std::string, std::string> Global::build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i].size() > 2 && args[i].substr(0, 2) == "-") {
            std::string key = args[i].substr(1);
            if (i + 1 < args.size()) {
                options[key] = args[i + 1];
                i++;
            }
        }
    }
    return options;
}

int Global::handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
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
