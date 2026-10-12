#include "people_management.h"
#include "common.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <sstream>

// Global implementation
const int Global::SUCCESS = 0;
const int Global::DB_OPEN_ERROR = 1;
const int Global::INVALID_OPTION = 2;
const int Global::NOT_ENOUGH_OPTIONS = 3;
const int Global::RECORD_NOT_EXISTS = 4;
const int Global::SQL_EXECUTION_ERROR = 5;
const int Global::FAILURE = 6;

bool Global::validate_options(const std::string& subcommand, const std::string& target) {
    if (target == "person") {
        if (subcommand == "add") return true;
        if (subcommand == "search") return true;
        if (subcommand == "delete") return true;
        if (subcommand == "update") return true;
    } else if (target == "school") {
        if (subcommand == "add") return true;
        if (subcommand == "search") return true;
        if (subcommand == "delete") return true;
        if (subcommand == "update") return true;
    } else if (target == "mentor") {
        if (subcommand == "assign" || subcommand == "lookup") return true;
    }
    return false;
}

std::map<std::string, std::string> Global::build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i].size() > 2 && args[i].substr(0, 2) == "-") {
            if (i + 1 < args.size() && args[i + 1].substr(0, 2) != "-") {
                options[args[i]] = args[i + 1];
                i++;
            } else {
                // For flags like 'assign' or 'lookup' in mentor subcommand
                options[args[i]] = "";
            }
        } else {
            // Handle subcommands like 'assign' or 'lookup' that don't start with '-'
            options[args[i]] = "";
        }
    }
    return options;
}

int Global::handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    if (subcommand == "add") {
        if (target == "person") {
            if (options.count("-name") && options.count("-age") && options.count("-school") && options.count("-type")) {
                people_management.add(target, options);
                return SUCCESS;
            }
            return NOT_ENOUGH_OPTIONS;
        } else if (target == "school") {
            if (options.count("-name")) {
                people_management.add(target, options);
                return SUCCESS;
            }
            return NOT_ENOUGH_OPTIONS;
        }
    } else if (subcommand == "search") {
        if (target == "person") {
            if (options.count("-name") || options.count("-age") || options.count("-school") || options.count("-type")) {
                people_management.search(target, options);
                return SUCCESS;
            }
            // If no options provided, search all
            people_management.search(target, {});
            return SUCCESS;
        } else if (target == "school") {
            people_management.search(target, options);
            return SUCCESS;
        }
    } else if (subcommand == "delete") {
        if (options.count("-id")) {
            people_management.delete_record(target, options);
            return SUCCESS;
        }
        return NOT_ENOUGH_OPTIONS;
    } else if (subcommand == "update") {
        if (options.count("-id")) {
            people_management.update(target, options);
            return SUCCESS;
        }
        return NOT_ENOUGH_OPTIONS;
    } else if (subcommand == "mentor") {
        if (target == "mentor") {
            if (options.count("assign")) {
                if (options.count("-student") && options.count("-mentor")) {
                    people_management.mentor(target, options);
                    return SUCCESS;
                }
                return NOT_ENOUGH_OPTIONS;
            } else if (options.count("lookup")) {
                if (options.count("-student") || options.count("-mentor")) {
                    people_management.mentor(target, options);
                    return SUCCESS;
                }
                return NOT_ENOUGH_OPTIONS;
            }
        }
    }
    return FAILURE;
}

PeopleManagement::PeopleManagement() : db(nullptr) {
    int rc = sqlite3_open(db_name, &db);
    if (rc != SQLITE_OK) {
        std::cerr << "Failed to open database." << std::endl;
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

void PeopleManagement::check_database(const char* db_name) const {
    // This function is kept for signature compliance but logic is handled in constructor
}

void PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) return;

    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();
    char* errMsg = nullptr;
    sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (errMsg) {
        sqlite3_free(errMsg);
    }
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << (i == argc - 1 ? "" : ", ");
    }
    std::cout << std::endl;
    return 0;
}

void PeopleManagement::check_select(const std::string sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
    }
}

void PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        std::string name = options.at("-name");
        std::string age = options.at("-age");
        std::string school = options.at("-school");
        std::string type = options.at("-type");
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" + name + "', " + age + ", " + school + ", " + type + ");";
    } else if (target == "school") {
        std::string name = options.at("-name");
        sql = "INSERT INTO school (name) VALUES ('" + name + "');";
    } else {
        return;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "Add Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return;
    }
    std::cout << "Record added successfully." << std::endl;
}

void PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM " + target;
    std::string where_clause = "";

    if (target == "person") {
        if (options.count("-name")) where_clause += " AND name LIKE '%" + options.at("-name") + "%'";
        if (options.count("-age")) where_clause += " AND age = " + options.at("-age");
        if (options.count("-school")) where_clause += " AND school = " + options.at("-school");
        if (options.count("-type")) where_clause += " AND type = " + options.at("-type");
    } else if (target == "school") {
        if (options.count("-name")) where_clause += " AND name LIKE '%" + options.at("-name") + "%'";
    }

    if (!where_clause.empty()) {
        sql += " WHERE 1=1" + where_clause;
    }

    check_select(sql);
}

void PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return;
    
    std::string id = options.at("-id");
    std::string sql = "DELETE FROM " + target + " WHERE ID = " + id + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "Delete Error: " << errMsg << std::endl;
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
    if (options.find("-id") == options.end()) return;
    
    std::string id = options.at("-id");
    std::string set_clause = "";

    if (target == "person") {
        if (options.count("-name")) set_clause += "name = '" + options.at("-name") + "', ";
        if (options.count("-age")) set_clause += "age = " + options.at("-age") + ", ";
        if (options.count("-school")) set_clause += "school = " + options.at("-school") + ", ";
        if (options.count("-type")) set_clause += "type = " + options.at("-type") + ", ";
    } else if (target == "school") {
        if (options.count("-name")) set_clause += "name = '" + options.at("-name") + "', ";
    }

    if (set_clause.empty()) return;
    set_clause.erase(set_clause.length() - 2); // Remove trailing comma

    std::string sql = "UPDATE " + target + " SET " + set_clause + " WHERE ID = " + id + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "Update Error: " << errMsg << std::endl;
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
    if (target != "mentor") return;

    if (options.count("assign")) {
        if (!options.count("-student") || !options.count("-mentor")) return;
        
        std::string student = options.at("-student");
        std::string mentor = options.at("-mentor");
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" + student + ", " + mentor + ");";

        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            if (errMsg) {
                std::cerr << "Mentor Assign Error: " << errMsg << std::endl;
                sqlite3_free(errMsg);
            }
            return;
        }
        std::cout << "Mentorship assigned successfully." << std::endl;
    } else if (options.count("lookup")) {
        std::string sql;
        if (options.count("-student")) {
            sql = "SELECT m.mentor, p.name FROM mentorship m JOIN people p ON m.mentor = p.ID WHERE m.student = " + options.at("-student") + ";";
        } else if (options.count("-mentor")) {
            sql = "SELECT p.name, p.ID FROM mentorship m JOIN people p ON m.student = p.ID WHERE m.mentor = " + options.at("-mentor") + ";";
        } else {
            return;
        }

        check_select(sql);
    }
}
