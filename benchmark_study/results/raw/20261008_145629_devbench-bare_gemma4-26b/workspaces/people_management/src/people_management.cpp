#include "people_management.h"
#include "utils.h"
#include <iostream>
#include <sstream>
#include <fstream>

PeopleManagement::PeopleManagement() : db(nullptr) {
    if (check_database(db_name.c_str())) {
        if (sqlite3_open(db_name.c_str(), &db) != SQLITE_OK) {
            db = nullptr;
        }
    }
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

bool PeopleManagement::check_database(const char* db_name) const {
    std::ifstream f(db_name.c_str());
    if (!f.good()) {
        // If database doesn't exist, we'll create it via sqlite3_open, 
        // but we need to run the schema files.
        return true; 
    }
    return true;
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

bool PeopleManagement::check_select(const std::string& sql) const {
    sqlite3_stmt* stmt;
    bool exists = false;
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            exists = true;
        }
    }
    sqlite3_finalize(stmt);
    return exists;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "person") {
        if (options.find("-name") == options.end() || options.find("-age") == options.end() ||
            options.find("-school") == options.end() || options.find("-type") == options.end()) {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        std::string sql = "INSERT INTO people (name, age, school, type) VALUES ('" +
                          options.at("-name") + "', " + options.at("-age") + ", " +
                          options.at("-school") + ", " + options.at("-type") + ");";
        char* errMsg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg) != SQLITE_OK) {
            std::cerr << "Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return Global::SQL_EXECUTION_ERROR;
        }
        std::cout << "Person added successfully." << std::endl;
    } else if (target == "school") {
        if (options.find("-name") == options.end()) {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        std::string sql = "INSERT INTO school (name) VALUES ('" + options.at("-name") + "');";
        char* errMsg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg) != SQLITE_OK) {
            std::cerr << "Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return Global::SQL_EXECUTION_ERROR;
        }
        std::cout << "School added successfully." << std::endl;
    } else {
        return Global::INVALID_OPTION;
    }
    return Global::SUCCESS;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string table = (target == "person") ? "people" : "school";
    std::string sql = "SELECT * FROM " + table + " WHERE 1=1";

    if (target == "person") {
        if (options.count("-name")) sql += " AND name = '" + options.at("-name") + "'";
        if (options.count("-age")) sql += " AND age = " + options.at("-age");
        if (options.count("-school")) sql += " AND school = " + options.at("-school");
        if (options.count("-type")) sql += " AND type = " + options.at("-type");
    } else if (target == "school") {
        if (options.count("-name")) sql += " AND name = '" + options.at("-name") + "'";
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), PeopleManagement::search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    return Global::SUCCESS;
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return Global::NOT_ENOUGH_OPTIONS;
    std::string table = (target == "person") ? "people" : "school";
    std::string sql = "DELETE FROM " + table + " WHERE id = " + options.at("-id") + ";";
    
    char* errMsg = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg) != SQLITE_OK) {
        std::cerr << "Error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record deleted." << std::endl;
    return Global::SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return Global::NOT_ENOUGH_OPTIONS;
    if (options.empty()) return Global::NOT_ENOUGH_OPTIONS;

    std::string table = (target == "person") ? "people" : "school";
    std::string sql = "UPDATE " + table + " SET ";
    
    bool first = true;
    for (auto const& [key, val] : options) {
        if (key == "-id") continue;
        if (!first) sql += ", ";
        std::string col = (key == "-name") ? "name" : (key == "-age") ? "age" : (key == "-school") ? "school" : (key == "-type") ? "type" : "";
        if (col.empty()) continue;
        
        if (col == "name") sql += col + " = '" + val + "'";
        else sql += col + " = " + val;
        first = false;
    }

    if (first) return Global::NOT_ENOUGH_OPTIONS;
    sql += " WHERE id = " + options.at("-id") + ";";

    char* errMsg = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg) != SQLITE_OK) {
        std::cerr << "Error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }
    std::cout << "Record updated." << std::endl;
    return Global::SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (options.find("-student") == options.end() || options.find("-mentor") == options.end()) {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" +
                          options.at("-student") + ", " + options.at("-mentor") + ");";
        char* errMsg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg) != SQLITE_OK) {
            std::cerr << "Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return Global::SQL_EXECUTION_ERROR;
        }
        std::cout << "Mentorship assigned." << std::endl;
        return Global::SUCCESS;
    } else if (target == "lookup") {
        std::string sql = "SELECT m.student, m.mentor, p.name FROM mentorship m JOIN people p ON m.student = p.id WHERE ";
        if (options.count("-student")) {
            sql += "m.student = " + options.at("-student");
        } else if (options.count("-mentor")) {
            sql += "m.mentor = " + options.at("-mentor");
        } else {
            return Global::NOT_ENOUGH_OPTIONS;
        }
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), PeopleManagement::search_callback, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            std::cerr << "Error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return Global::SQL_EXECUTION_ERROR;
        }
        return Global::SUCCESS;
    }
    return Global::FAILURE;
}

int PeopleManagement::search_callback(void* data, int argc, char** argv, char** azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << (i == argc - 1 ? "" : ", ");
    }
    std::cout << std::endl;
    return 0;
}

namespace Global {
    bool validate_options(const std::string& subcommand, const std::string& target) {
        return true; // Simplified for this implementation
    }

    std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
        std::map<std::string, std::string> options;
        for (size_t i = 0; i < args.size(); ++i) {
            if (args[i].size() > 1 && args[i][0] == '-') {
                std::string key = args[i];
                if (i + 1 < args.size()) {
                    options[key] = args[i + 1];
                    i++;
                }
            }
        }
        return options;
    }

    int handle_options(const std::string& subcommand, const std::string& target, 
                       const std::map<std::string, std::string>& options, 
                       const PeopleManagement& people_management) {
        if (subcommand == "add") return people_management.add(target, options);
        if (subcommand == "search") return people_management.search(target, options);
        if (subcommand == "delete") return people_management.delete_record(target, options);
        if (subcommand == "update") return people_management.update(target, options);
        if (subcommand == "mentor") return people_management.mentor(target, options);
        return FAILURE;
    }
}
