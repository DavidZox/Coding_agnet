#include "people_management.h"
#include "common.h"
#include "utils.h"
#include <sqlite3.h>
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <map>

PeopleManagement::PeopleManagement() : db(nullptr) {
    check_database(Global::db_name.c_str());
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

void PeopleManagement::check_database(const char* db_name) {
    int rc = sqlite3_open(db_name, &db);
    if (rc) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
    } else {
        execute_sql_from_file(Global::people_sql_name.c_str());
        execute_sql_from_file(Global::school_sql_name.c_str());
        execute_sql_from_file(Global::mentorship_sql_name.c_str());
    }
}

void PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        return;
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();
    char* errMsg = nullptr;
    sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (errMsg) {
        sqlite3_free(errMsg);
    }
}

void PeopleManagement::check_select(const std::string sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
    }
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << " ";
    }
    std::cout << std::endl;
    return 0;
}

void PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        if (options.find("name") == options.end() || options.find("age") == options.end() ||
            options.find("school") == options.end() || options.find("type") == options.end()) {
            return;
        }
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" +
              options.at("name") + "', " + options.at("age") + ", " +
              options.at("school") + ", " + options.at("type") + ");";
    } else if (target == "school") {
        if (options.find("name") == options.end()) {
            return;
        }
        sql = "INSERT INTO school (name) VALUES ('" + options.at("name") + "');";
    } else {
        return;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return;
    }
    std::cout << "Record added successfully." << std::endl;
}

void PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM " + target;
    std::vector<std::string> conditions;

    if (target == "person") {
        if (options.count("name")) conditions.push_back("name = '" + options.at("name") + "'");
        if (options.count("age")) conditions.push_back("age = " + options.at("age"));
        if (options.count("school")) conditions.push_back("school = " + options.at("school"));
        if (options.count("type")) conditions.push_back("type = " + options.at("type"));
    } else if (target == "school") {
        if (options.count("name")) conditions.push_back("name = '" + options.at("name") + "'");
    }

    if (!conditions.empty()) {
        sql += " WHERE ";
        for (size_t i = 0; i < conditions.size(); ++i) {
            sql += conditions[i] + (i == conditions.size() - 1 ? "" : " AND ");
        }
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
    }
}

void PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) return;
    
    std::string sql = "DELETE FROM " + target + " WHERE ID = " + options.at("id") + ";";
    
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return;
    }
    
    if (sqlite3_changes(db) == 0) {
        return;
    }
    
    std::cout << "Record deleted successfully." << std::endl;
}

void PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("id") == options.end()) return;
    
    std::string id = options.at("id");
    std::string set_clause = "";
    
    if (target == "person") {
        if (options.count("name")) set_clause += "name = '" + options.at("name") + "', ";
        if (options.count("age")) set_clause += "age = " + options.at("age") + ", ";
        if (options.count("school")) set_clause += "school = " + options.at("school") + ", ";
        if (options.count("type")) set_clause += "type = " + options.at("type") + ", ";
    } else if (target == "school") {
        if (options.count("name")) set_clause += "name = '" + options.at("name") + "', ";
    }

    if (set_clause.empty()) return;
    set_clause.erase(set_clause.length() - 2); // remove last comma

    std::string sql = "UPDATE " + target + " SET " + set_clause + " WHERE ID = " + id + ";";
    
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return;
    }

    if (sqlite3_changes(db) == 0) {
        return;
    }

    std::cout << "Record updated successfully." << std::endl;
}

void PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (options.find("student") == options.end() || options.find("mentor") == options.end()) {
            return;
        }
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" +
                          options.at("student") + ", " + options.at("mentor") + ");";
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            if (errMsg) {
                std::cerr << "SQL Error: " << errMsg << std::endl;
                sqlite3_free(errMsg);
            }
            return;
        }
        std::cout << "Mentorship assigned successfully." << std::endl;
    } else if (target == "lookup") {
        std::string sql;
        if (options.count("student")) {
            sql = "SELECT m.mentor, p.name FROM mentorship m JOIN people p ON m.mentor = p.ID WHERE m.student = " + options.at("student") + ";";
        } else if (options.count("mentor")) {
            sql = "SELECT m.student, p.name FROM mentorship m JOIN people p ON m.student = p.ID WHERE m.mentor = " + options.at("mentor") + ";";
        } else {
            return;
        }

        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            if (errMsg) {
                std::cerr << "SQL Error: " << errMsg << std::endl;
                sqlite3_free(errMsg);
            }
        }
    }
}

bool Global::validate_options(const std::string& subcommand, const std::string& target) {
    if (target == "person") {
        if (subcommand == "add") {
            return true; // Handled in add() logic
        } else if (subcommand == "search") {
            return true;
        } else if (subcommand == "update") {
            return true;
        }
    } else if (target == "school") {
        if (subcommand == "add" || subcommand == "search" || subcommand == "update") {
            return true;
        }
    } else if (subcommand == "mentor") {
        return true;
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
        if (target == "person") {
            if (options.count("name") && options.count("age") && options.count("school") && options.count("type")) {
                people_management.add(target, options);
                return SUCCESS;
            }
        } else if (target == "school") {
            if (options.count("name")) {
                people_management.add(target, options);
                return SUCCESS;
            }
        }
        return NOT_ENOUGH_OPTIONS;
    } else if (subcommand == "search") {
        if (target == "person" || target == "school") {
            people_management.search(target, options);
            return SUCCESS;
        }
    } else if (subcommand == "delete") {
        if (options.count("id")) {
            std::map<std::string, std::string> del_opts = options;
            people_management.delete_record(target, del_opts);
            return SUCCESS;
        }
        return NOT_ENOUGH_OPTIONS;
    } else if (subcommand == "update") {
        if (options.count("id")) {
            people_management.update(target, options);
            return SUCCESS;
        }
        return NOT_ENOUGH_OPTIONS;
    } else if (subcommand == "mentor") {
        if (options.count("assign")) {
            // The subcommand logic for mentor is slightly different in the CLI structure
            // Based on PRD: ./UMM mentor assign -student STUDENT_ID -mentor FACULTY_ID
            // Here 'target' passed to handle_options would be 'assign'
            if (target == "assign") {
                if (options.count("student") && options.count("mentor")) {
                    people_management.mentor("assign", options);
                    return SUCCESS;
                }
                return NOT_ENOUGH_OPTIONS;
            }
        } else if (options.count("lookup")) {
            if (target == "lookup") {
                if (options.count("student") || options.count("mentor")) {
                    people_management.mentor("lookup", options);
                    return SUCCESS;
                }
                return NOT_ENOUGH_OPTIONS;
            }
        }
    }
    return FAILURE;
}
