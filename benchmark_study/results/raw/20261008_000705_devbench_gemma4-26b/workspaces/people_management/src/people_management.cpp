#include "people_management.h"
#include "common.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <sqlite3.h>
#include <map>

PeopleManagement::PeopleManagement() : db(nullptr) {
    // Open the database first
    int rc = sqlite3_open(db_name.c_str(), &db);
    if (rc != SQLITE_OK) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        db = nullptr;
    } else {
        // Initialize schema
        execute_sql_from_file(people_sql_name.c_str());
        execute_sql_from_file(school_sql_name.c_str());
        execute_sql_from_file(mentorship_sql_name.c_str());
    }
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

void PeopleManagement::check_database(const char* db_name) const {
    sqlite3* temp_db = nullptr;
    int rc = sqlite3_open(db_name, &temp_db);
    if (rc != SQLITE_OK) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(temp_db) << std::endl;
    }
    if (temp_db) {
        sqlite3_close(temp_db);
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
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL error in " << file_name << ": " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
    }
    file.close();
}

void PeopleManagement::check_select(const std::string sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "SQL error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
    }
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << (i == argc - 1 ? "" : ", ");
    }
    std::cout << std::endl;
    return SQLITE_OK;
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
            std::cerr << "Add error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return;
    }
    std::cout << "Record added successfully." << std::endl;
}

void PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM " + target;
    std::string where_clause = "";

    if (!options.empty()) {
        where_clause = " WHERE ";
        bool first = true;
        for (auto const& [key, val] : options) {
            if (key == "-name") {
                where_clause += (first ? "" : " AND ") + std::string("name = '") + val + "'";
            } else if (key == "-age") {
                where_clause += (first ? "" : " AND ") + std::string("age = ") + val;
            } else if (key == "-school") {
                where_clause += (first ? "" : " AND ") + std::string("school = ") + val;
            } else if (key == "-type") {
                where_clause += (first ? "" : " AND ") + std::string("type = ") + val;
            } else if (key == "-id") {
                where_clause += (first ? "" : " AND ") + std::string("ID = ") + val;
            }
            first = false;
        }
    }

    sql += where_clause + ";";
    check_select(sql);
}

void PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return;
    
    std::string sql = "DELETE FROM " + target + " WHERE ID = " + options.at("-id") + ";";
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "Delete error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return;
    }
    std::cout << "Record deleted successfully." << std::endl;
}

void PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return;
    if (options.size() <= 1) return;

    std::string sql = "UPDATE " + target + " SET ";
    bool first = true;
    for (auto const& [key, val] : options) {
        if (key == "-id") continue;
        if (!first) sql += ", ";
        if (key == "-name") sql += "name = '" + val + "'";
        else if (key == "-age") sql += "age = " + val;
        else if (key == "-school") sql += "school = " + val;
        else if (key == "-type") sql += "type = " + val;
        else continue;
        first = false;
    }
    sql += " WHERE ID = " + options.at("-id") + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        if (errMsg) {
            std::cerr << "Update error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
        }
        return;
    }
    std::cout << "Record updated successfully." << std::endl;
}

void PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (options.find("-student") == options.end() || options.find("-mentor") == options.end()) {
            return;
        }
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" + 
                          options.at("-student") + ", " + options.at("-mentor") + ");";
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            if (errMsg) {
                std::cerr << "Mentor assign error: " << errMsg << std::endl;
                sqlite3_free(errMsg);
            }
            return;
        }
        std::cout << "Mentorship assigned successfully." << std::endl;
    } else if (target == "lookup") {
        std::string sql = "SELECT m.ID, m.student, m.mentor FROM mentorship m ";
        if (options.find("-student") != options.end()) {
            sql += "WHERE m.student = " + options.at("-student") + ";";
        } else if (options.find("-mentor") != options.end()) {
            sql += "WHERE m.mentor = " + options.at("-mentor") + ";";
        } else {
            return;
        }
        check_select(sql);
    }
}

bool validate_options(const std::string& subcommand, const std::string& target) {
    if (subcommand == "add") {
        if (target == "person") {
            return true; // Simplified for implementation
        } else if (target == "school") {
            return true;
        }
    } else if (subcommand == "search") {
        if (target == "person" || target == "school") return true;
    } else if (subcommand == "delete") {
        if (target == "person" || target == "school") return true;
    } else if (subcommand == "update") {
        if (target == "person" || target == "school") return true;
    } else if (subcommand == "mentor") {
        return true;
    }
    return false;
}

std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i].size() > 1 && args[i][0] == '-' && i + 1 < args.size()) {
            options[args[i]] = args[i + 1];
            i++;
        } else if (args[i].size() > 1 && args[i][0] == '-' && i + 1 == args.size()) {
            options[args[i]] = "";
        }
    }
    return options;
}

int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    if (subcommand == "add") {
        if (target == "person") {
            if (options.count("-name") && options.count("-age") && options.count("-school") && options.count("-type")) {
                people_management.add(target, options);
                return 0;
            }
        } else if (target == "school") {
            if (options.count("-name")) {
                people_management.add(target, options);
                return 0;
            }
        }
        return 3; // NOT_ENOUGH_OPTIONS
    } else if (subcommand == "search") {
        people_management.search(target, options);
        return 0;
    } else if (subcommand == "delete") {
        if (options.count("-id")) {
            people_management.delete_record(target, options);
            return 0;
        }
        return 3;
    } else if (subcommand == "update") {
        if (options.count("-id")) {
            people_management.update(target, options);
            return 0;
        }
        return 3;
    } else if (subcommand == "mentor") {
        // target here is 'assign' or 'lookup'
        people_management.mentor(target, options);
        return 0;
    }
    return 6; // FAILURE
}
