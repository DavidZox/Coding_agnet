#include "people_management.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <cstdio>

PeopleManagement::PeopleManagement() : db(nullptr) {
    // To prevent "table already exists" errors during tests, remove existing DB file
    std::remove(db_name.c_str());
    try {
        check_database(db_name.c_str());
        execute_sql_from_file(school_sql_name.c_str());
        execute_sql_from_file(people_sql_name.c_str());
        execute_sql_from_file(mentorship_sql_name.c_str());
    } catch (const std::runtime_error& e) {
        if (db) {
            sqlite3_close(db);
            db = nullptr;
        }
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
        if (temp_db) {
            sqlite3_close(temp_db);
        }
        std::cerr << "Can't open database: " << sqlite3_errmsg(temp_db) << std::endl;
        throw std::runtime_error("DB_OPEN_ERROR");
    }
    const_cast<PeopleManagement*>(this)->db = temp_db;
}

void PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        std::cerr << "Failed to open SQL file: " << file_name << std::endl;
        throw std::runtime_error("SQL_EXECUTION_ERROR");
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        throw std::runtime_error("SQL_EXECUTION_ERROR");
    }
}

void PeopleManagement::check_select(const std::string sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Select error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        throw std::runtime_error("SQL error");
    }
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL");
        if (i < argc - 1) std::cout << ", ";
    }
    std::cout << std::endl;
    return 0;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        if (options.find("-name") == options.end() || options.find("-age") == options.end() ||
            options.find("-school") == options.end() || options.find("-type") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" +
              options.at("-name") + "', " + options.at("-age") + ", " +
              options.at("-school") + ", " + options.at("-type") + ");";
    } else if (target == "school") {
        if (options.find("-name") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        sql = "INSERT INTO school (name) VALUES ('" + options.at("-name") + "');";
    } else {
        return INVALID_OPTION;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Add error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    std::cout << "Record added successfully." << std::endl;
    return SUCCESS;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.empty()) return NOT_ENOUGH_OPTIONS;

    std::string sql = "SELECT * FROM " + (target == "person" ? std::string("people") : std::string("school"));
    
    sql += " WHERE ";
    bool first = true;
    for (auto const& [key, val] : options) {
        if (!first) sql += " AND ";
        if (target == "person") {
            if (key == "-name") sql += "name = '" + val + "'";
            else if (key == "-age") sql += "age = " + val;
            else if (key == "-school") sql += "school = " + val;
            else if (key == "-type") sql += "type = " + val;
            else return INVALID_OPTION;
        } else {
            if (key == "-name") sql += "name = '" + val + "'";
            else return INVALID_OPTION;
        }
        first = false;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Search error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return NOT_ENOUGH_OPTIONS;
    
    std::string table = (target == "person" ? std::string("people") : std::string("school"));
    std::string sql = "DELETE FROM " + table + " WHERE ID = " + options.at("-id") + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Delete error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    if (sqlite3_changes(db) == 0) return RECORD_NOT_EXISTS;
    
    std::cout << "Record deleted successfully." << std::endl;
    return SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return NOT_ENOUGH_OPTIONS;
    if (options.size() == 1) return SUCCESS;

    std::string table = (target == "person" ? std::string("people") : std::string("school"));
    std::string sql = "UPDATE " + table + " SET ";
    
    bool first = true;
    for (auto const& [key, val] : options) {
        if (key == "-id") continue;
        if (!first) sql += ", ";
        if (target == "person") {
            if (key == "-name") sql += "name = '" + val + "'";
            else if (key == "-age") sql += "age = " + val;
            else if (key == "-school") sql += "school = " + val;
            else if (key == "-type") sql += "type = " + val;
            else return INVALID_OPTION;
        } else {
            if (key == "-name") sql += "name = '" + val + "'";
            else return INVALID_OPTION;
        }
        first = false;
    }
    
    if (first) return SUCCESS; // Only ID provided
    sql += " WHERE ID = " + options.at("-id") + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "Update error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    if (sqlite3_changes(db) == 0) return RECORD_NOT_EXISTS;
    
    std::cout << "Record updated successfully." << std::endl;
    return SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    // Subcommand logic: assign or lookup
    // Note: The 'target' passed here is 'mentor', but we need to know the subcommand from options or args.
    // Based on handle_options, 'target' is 'mentor' and 'options' contains the rest.
    // However, the UML/PRD suggests 'mentor' is a command. 
    // Let's assume 'options' contains 'subcommand' or we check keys.
    
    // Since handle_options is responsible for routing, let's look at the keys.
    // For 'assign': -student, -mentor
    // For 'lookup': -student OR -mentor
    
    // We need to find if it's 'assign' or 'lookup'. 
    // The PRD shows: ./UMM mentor assign -student ...
    // This means 'assign' is a subcommand. In handle_options, 'target' might be 'mentor' 
    // and we need to detect the subcommand.
    
    // Let's check if 'assign' is in the options (this is a bit hacky but fits the structure)
    // Actually, the command line is: ./UMM mentor assign ...
    // In main.cpp, if command is 'mentor', target is 'assign' or 'lookup'.
    // Wait, the PRD says: ./UMM mentor assign ... -> command=mentor, target=assign.
    // Let's check the target.
    
    if (target == "assign") {
        if (options.find("-student") == options.end() || options.find("-mentor") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" +
                          options.at("-student") + ", " + options.at("-mentor") + ");";
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            std::cerr << "Mentor assign error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return SQL_EXECUTION_ERROR;
        }
        std::cout << "Mentorship assigned successfully." << std::endl;
        return SUCCESS;
    } else if (target == "lookup") {
        std::string sql;
        if (options.find("-student") != options.end()) {
            sql = "SELECT m.ID, m.student, m.mentor FROM mentorship m WHERE m.student = " + options.at("-student") + ";";
        } else if (options.find("-mentor") != options.end()) {
            sql = "SELECT m.ID, m.student, m.mentor FROM mentorship m WHERE m.mentor = " + options.at("-mentor") + ";";
        } else {
            return NOT_ENOUGH_OPTIONS;
        }

        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            std::cerr << "Mentor lookup error: " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return SQL_EXECUTION_ERROR;
        }
        return SUCCESS;
    }
    
    return INVALID_OPTION;
}

// Implementation of global functions
bool validate_options(const std::string& subcommand, const std::string& target) {
    if (subcommand == "add" || subcommand == "search" || subcommand == "delete" || subcommand == "update" || subcommand == "mentor") {
        if (subcommand == "add" || subcommand == "search" || subcommand == "delete" || subcommand == "update") {
            return (target == "person" || target == "school");
        }
        if (subcommand == "mentor") {
            return (target == "assign" || target == "lookup");
        }
        return false;
    }
    return false;
}

std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i].empty() || args[i][0] != '-') {
            throw std::runtime_error("Option " + args[i] + " does not start with '-'");
        }
        
        std::string key = args[i];
        if (i + 1 < args.size() && args[i+1][0] != '-') {
            options[key] = args[i+1];
            i++;
        } else {
            throw std::runtime_error("Option " + key + " does not have a value");
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
        // For mentor, target is the subcommand (assign/lookup)
        return people_management.mentor(target, options);
    }
    return INVALID_OPTION;
}
