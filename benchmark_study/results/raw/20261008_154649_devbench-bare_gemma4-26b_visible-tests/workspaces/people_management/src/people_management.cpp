#include "people_management.h"
#include "utils.h"
#include <iostream>
#include <sstream>
#include <stdexcept>

PeopleManagement::PeopleManagement() : db(nullptr) {
    if (!check_database(db_name)) {
        throw std::runtime_error("Failed to open database");
    }
    execute_sql_from_file(people_sql_name);
    execute_sql_from_file(school_sql_name);
    execute_sql_from_file(mentorship_sql_name);
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

bool PeopleManagement::check_database(const char* db_name) const {
    int rc = sqlite3_open(db_name, &db);
    return rc == SQLITE_OK;
}

bool PeopleManagement::execute_sql_from_file(const char* file_name) const {
    char* err_msg = nullptr;
    std::ifstream file(file_name);
    if (!file.is_open()) return false;

    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();

    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK) {
        if (err_msg) sqlite3_free(err_msg);
        return false;
    }
    return true;
}

bool PeopleManagement::check_select(const std::string sql) const {
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) return false;
    bool exists = (sqlite3_step(stmt) == SQLITE_ROW);
    sqlite3_finalize(stmt);
    return exists;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "school") {
        if (options.find("-name") == options.end()) return NOT_ENOUGH_OPTIONS;
        std::string sql = "INSERT INTO school (name) VALUES ('" + options.at("-name") + "');";
        char* err_msg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_msg) != SQLITE_OK) return SQL_EXECUTION_ERROR;
        return SUCCESS;
    } else if (target == "person") {
        if (options.find("-name") == options.end() || options.find("-age") == options.end() ||
            options.find("-school") == options.end() || options.find("-type") == options.end()) {
            return NOT_ENOUGH_OPTIONS;
        }
        
        int school_id = std::stoi(options.at("-school"));
        std::string check_sql = "SELECT id FROM school WHERE id = " + std::to_string(school_id) + ";";
        if (!check_select(check_sql)) return RECORD_NOT_EXISTS;

        std::string sql = "INSERT INTO people (name, age, school, type) VALUES ('" +
                          options.at("-name") + "', " + options.at("-age") + ", " +
                          school_id + ", " + options.at("-type") + ");";
        char* err_msg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_msg) != SQLITE_OK) return SQL_EXECUTION_ERROR;
        return SUCCESS;
    }
    return FAILURE;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql = "SELECT * FROM ";
    if (target == "person") sql += "people";
    else if (target == "school") sql += "school";
    else return FAILURE;

    if (!options.empty()) {
        sql += " WHERE ";
        std::vector<std::string> conditions;
        for (auto const& [key, val] : options) {
            if (key == "-name") conditions.push_back("name = '" + val + "'");
            else if (key == "-age") conditions.push_back("age = " + val);
            else if (key == "-school") conditions.push_back("school = " + val);
            else if (key == "-type") conditions.push_back("type = " + val);
            else if (key == "-id") conditions.push_back("id = " + val);
            else return INVALID_OPTION;
        }
        for (size_t i = 0; i < conditions.size(); ++i) {
            sql += conditions[i] + (i == conditions.size() - 1 ? "" : " AND ");
        }
    }

    char* err_msg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, (void*)1, &err_msg);
    if (rc != SQLITE_OK) return SQL_EXECUTION_ERROR;
    return SUCCESS;
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return NOT_ENOUGH_OPTIONS;
    std::string id = options.at("-id");
    
    std::string check_sql = "SELECT id FROM " + std::string(target == "person" ? "people" : "school") + " WHERE id = " + id + ";";
    if (!check_select(check_sql)) return RECORD_NOT_EXISTS;

    std::string sql = "DELETE FROM " + std::string(target == "person" ? "people" : "school") + " WHERE id = " + id + ";";
    char* err_msg = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_msg) != SQLITE_OK) return SQL_EXECUTION_ERROR;
    return SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.find("-id") == options.end()) return NOT_ENOUGH_OPTIONS;
    std::string id = options.at("-id");
    std::string table = (target == "person" ? "people" : "school");

    std::string check_sql = "SELECT id FROM " + table + " WHERE id = " + id + ";";
    if (!check_select(check_sql)) return RECORD_NOT_EXISTS;

    std::string set_clause = "";
    for (auto const& [key, val] : options) {
        if (key == "-id") continue;
        if (key == "-name") set_clause += "name = '" + val + "', ";
        else if (key == "-age") set_clause += "age = " + val + ", ";
        else if (key == "-school") set_clause += "school = " + val + ", ";
        else if (key == "-type") set_clause += "type = " + val + ", ";
        else return INVALID_OPTION;
    }

    if (set_clause.empty()) return NOT_ENOUGH_OPTIONS;
    set_clause.erase(set_clause.length() - 2); // remove last comma

    std::string sql = "UPDATE " + table + " SET " + set_clause + " WHERE id = " + id + ";";
    char* err_msg = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_msg) != SQLITE_OK) return SQL_EXECUTION_ERROR;
    return SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (options.find("-student") == options.end() || options.find("-mentor") == options.end()) return NOT_ENOUGH_OPTIONS;
        std::string s_id = options.at("-student");
        std::string m_id = options.at("-mentor");

        auto check_p = [&](const std::string& sql) { return check_select(sql); };
        if (!check_p("SELECT id FROM people WHERE id = " + s_id + ";")) return RECORD_NOT_EXISTS;
        if (!check_p("SELECT id FROM people WHERE id = " + m_id + " AND type = 2;")) return RECORD_NOT_EXISTS;

        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" + s_id + ", " + m_id + ");";
        char* err_msg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_msg) != SQLITE_OK) return SQL_EXECUTION_ERROR;
        return SUCCESS;
    } else if (target == "lookup") {
        if (options.find("-student") == options.end() && options.find("-mentor") == options.end()) return NOT_ENOUGH_OPTIONS;
        if (options.size() > 1) return INVALID_OPTION;

        std::string sql = "SELECT p.name FROM people p JOIN mentorship m ON p.id = m.student WHERE ";
        if (options.count("-student")) sql += "m.student = " + options.at("-student");
        else sql = "SELECT p.name FROM people p JOIN mentorship m ON p.mentor = m.mentor WHERE m.mentor = " + options.at("-mentor");

        char* err_msg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err_msg) != SQLITE_OK) return SQL_EXECUTION_ERROR;
        return SUCCESS;
    }
    return FAILURE;
}

int PeopleManagement::search_callback(void* data, int argc, char** argv, char** azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << " ";
    }
    std::cout << std::endl;
    return 0;
}

bool validate_options(const std::string& subcommand, const std::string& target) {
    if (subcommand == "mentor") return (target == "assign" || target == "lookup");
    if (subcommand == "add") return (target == "person" || target == "school");
    if (subcommand == "search" || subcommand == "delete" || subcommand == "update") 
        return (target == "person" || target == "school");
    return false;
}

std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
    if (args.size() % 2 != 0) throw std::runtime_error("Odd number of arguments");
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); i += 2) {
        if (args[i][0] != '-') throw std::runtime_error("Option " + args[i] + " does not start with '-'");
        if (i + 1 >= args.size()) throw std::runtime_error("Option " + args[i] + " does not have a value");
        options[args[i]] = args[i+1];
    }
    return options;
}

int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
    if (!validate_options(subcommand, target)) return INVALID_OPTION;

    if (subcommand == "add") return people_management.add(target, options);
    if (subcommand == "search") return people_management.search(target, options);
    if (subcommand == "delete") return people_management.delete_record(target, options);
    if (subcommand == "update") return people_management.update(target, options);
    if (subcommand == "mentor") return people_management.mentor(target, options);

    return FAILURE;
}
