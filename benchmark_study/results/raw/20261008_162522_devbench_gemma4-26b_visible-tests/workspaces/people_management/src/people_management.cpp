#include "people_management.h"
#include "common.h"
#include <iostream>
#include <fstream>
#include <sstream>

PeopleManagement::PeopleManagement() : db(nullptr) {
    if (check_database(db_name.c_str()) == SUCCESS) {
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

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    if (target == "person") {
        auto it_name = options.find("-name");
        auto it_age = options.find("-age");
        auto it_school = options.find("-school");
        auto it_type = options.find("-type");

        if (it_name == options.end() || it_age == options.end() || it_school == options.end() || it_type == options.end()) {
            return INVALID_OPTION;
        }

        std::string name = it_name->second;
        std::string age = it_age->second;
        std::string school = it_school->second;
        std::string type = it_type->second;
        sql = "INSERT INTO people (name, age, school, type) VALUES ('" + name + "', " + age + ", " + school + ", " + type + ");";
    } else if (target == "school") {
        auto it_name = options.find("-name");
        if (it_name == options.end()) return INVALID_OPTION;
        
        std::string name = it_name->second;
        sql = "INSERT INTO school (name) VALUES ('" + name + "');";
    } else {
        return FAILURE;
    }

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << (errMsg ? errMsg : "unknown error") << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    std::cout << "Record added successfully." << std::endl;
    return SUCCESS;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (options.empty()) return NOT_ENOUGH_OPTIONS;
    std::string sql = "SELECT * FROM ";
    if (target == "person") {
        sql += "people";
    } else if (target == "school") {
        sql += "school";
    } else {
        return FAILURE;
    }

    std::string where_clause = "";
    if (!options.empty()) {
        std::vector<std::string> conditions;
        for (auto it = options.begin(); it != options.end(); ++it) {
            if (it->first == "-name") conditions.push_back("name = '" + it->second + "'");
            else if (it->first == "-age") conditions.push_back("age = " + it->second);
            else if (it->first == "-school") conditions.push_back("school = " + it->second);
            else if (it->first == "-type") conditions.push_back("type = " + it->second);
            else if (it->first == "-id") conditions.push_back("ID = " + it->second);
        }
        
        if (!conditions.empty()) {
            where_clause = " WHERE ";
            for (size_t i = 0; i < conditions.size(); ++i) {
                where_clause += conditions[i];
                if (i < conditions.size() - 1) where_clause += " AND ";
            }
        }
    }
    sql += where_clause + ";";

    return check_select(sql);
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    auto it_id = options.find("-id");
    if (it_id == options.end()) return NOT_ENOUGH_OPTIONS;
    
    std::string table_name = (target == "person") ? "people" : target;
    std::string sql = "DELETE FROM " + table_name + " WHERE ID = " + it_id->second + ";";
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    if (sqlite3_changes(db) == 0) return RECORD_NOT_EXISTS;
    
    std::cout << "Record deleted successfully." << std::endl;
    return SUCCESS;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    auto it_id = options.find("-id");
    if (it_id == options.end()) return NOT_ENOUGH_OPTIONS;
    
    // Check if there are any other options to update
    bool has_update_fields = false;
    for (auto const& [key, val] : options) {
        if (key != "-id") {
            has_update_fields = true;
            break;
        }
    }
    if (!has_update_fields) return NOT_ENOUGH_OPTIONS;

    std::string table_name = (target == "person") ? "people" : target;
    std::string sql = "UPDATE " + table_name + " SET ";
    bool first = true;
    for (auto const& [key, val] : options) {
        if (key == "-id") continue;
        if (!first) sql += ", ";
        if (key == "-name") sql += "name = '" + val + "'";
        else if (key == "-age") sql += "age = " + val;
        else if (key == "-school") sql += "school = " + val;
        else if (key == "-type") sql += "type = " + val;
        else return INVALID_OPTION;
        first = false;
    }
    sql += " WHERE ID = " + it_id->second + ";";

    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    if (sqlite3_changes(db) == 0) return RECORD_NOT_EXISTS;

    std::cout << "Record updated successfully." << std::endl;
    return SUCCESS;
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        auto it_student = options.find("-student");
        auto it_mentor = options.find("-mentor");
        if (it_student == options.end() || it_mentor == options.end()) return INVALID_OPTION;
        
        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (" + it_student->second + ", " + it_mentor->second + ");";
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            sqlite3_free(errMsg);
            return SQL_EXECUTION_ERROR;
        }
        std::cout << "Mentorship assigned successfully." << std::endl;
        return SUCCESS;
    } else if (target == "lookup") {
        std::string sql;
        auto it_student = options.find("-student");
        auto it_mentor = options.find("-mentor");
        if (it_student != options.end()) {
            sql = "SELECT m.mentor, p.name FROM mentorship m JOIN people p ON m.mentor = p.ID WHERE m.student = " + it_student->second + ";";
        } else if (it_mentor != options.end()) {
            sql = "SELECT p.name, p.age, p.school, p.type FROM people p JOIN mentorship m ON p.ID = m.student WHERE m.mentor = " + it_mentor->second + ";";
        } else {
            return NOT_ENOUGH_OPTIONS;
        }

        struct CallbackData {
            int count;
        };
        CallbackData data = {0};

        auto lookup_callback = [](void *data, int argc, char **argv, char **azColName) -> int {
            static_cast<CallbackData*>(data)->count++;
            return 0;
        };

        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), lookup_callback, &data, &errMsg);
        if (rc != SQLITE_OK) {
            if (errMsg) sqlite3_free(errMsg);
            return SQL_EXECUTION_ERROR;
        }

        if (data.count == 0) {
            return RECORD_NOT_EXISTS;
        }

        return check_select(sql);
    }
    return FAILURE;
}

int PeopleManagement::check_select(const std::string sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), search_callback, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << (errMsg ? errMsg : "unknown error") << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::check_database(const char* db_name) {
    int rc = sqlite3_open(db_name, &db);
    if (rc != SQLITE_OK) {
        std::cerr << "Cannot open database: " << sqlite3_errmsg(db) << std::endl;
        return DB_OPEN_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) return FAILURE;
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string sql = buffer.str();
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::string error_msg = errMsg ? errMsg : "";
        sqlite3_free(errMsg);
        if (error_msg.find("already exists") != std::string::npos) {
            return SUCCESS;
        }
        std::cerr << "SQL error in " << file_name << ": " << error_msg << std::endl;
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << (i == argc - 1 ? "" : ", ");
    }
    std::cout << std::endl;
    return 0;
}
