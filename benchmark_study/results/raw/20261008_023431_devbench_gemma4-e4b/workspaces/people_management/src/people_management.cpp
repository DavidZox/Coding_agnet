#include "people_management.h"
#include "utils.h"
#include <sqlite3.h>
#include <iostream>
#include <fstream>
#include <sstream>
#include <map>
#include <vector>
#include <utility> // For std::pair

// --- Private Helper Functions Implementation ---

/**
 * @brief Checks if the database file exists and attempts to open it.
 * @param db_name The name of the database file.
 * @return true if the database is opened successfully, false otherwise.
 */
bool PeopleManagement::check_database(const char* db_name) const {
    sqlite3* db_check = nullptr;
    int rc = sqlite3_open(db_name, &db_check);
    if (rc != SQLITE_OK) {
        std::cerr << "Error opening database: " << sqlite3_errmsg(db_check) << std::endl;
        if (db_check) sqlite3_close(db_check);
        return false;
    }
    sqlite3_close(db_check);
    return true;
}

/**
 * @brief Executes SQL commands from a file to set up the schema.
 * @param file_name The path to the SQL schema file.
 * @return true on success, false on failure.
 */
bool PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream file(file_name);
    if (!file.is_open()) {
        std::cerr << "Error: Could not open SQL file: " << file_name << std::endl;
        return false;
    }

    std::string line;
    while (std::getline(file, line)) {
        // Trim whitespace and skip empty lines/comments
        size_t first = line.find_first_not_of(" \t\r\n");
        if (std::string::npos == first) continue;
        std::string trimmed_line = line.substr(first);
        if (trimmed_line.empty() || trimmed_line[0] == '--' || trimmed_line[0] == '/') continue;

        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, trimmed_line.c_str(), 0, 0, &errMsg);

        if (rc != SQLITE_OK) {
            std::cerr << "SQL error in file " << file_name << ": " << errMsg << std::endl;
            sqlite3_free(errMsg);
            return false;
        }
    }
    std::cout << "Schema loaded successfully from " << file_name << std::endl;
    return true;
}

/**
 * @brief Callback function for SELECT queries to print results.
 */
static int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    // data is a pointer to the target string (e.g., "person")
    const char* target = static_cast<const char*>(data);
    std::cout << "--- Results for " << target << " ---" << std::endl;
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << ": " << (argv[i] ? argv[i] : "NULL") << " | ";
    }
    std::cout << "\n---------------------------------" << std::endl;
    return 0; // Return 0 to continue iteration
}

// --- Constructor ---
PeopleManagement::PeopleManagement() : db(nullptr) {
    // Check if DB can be opened/created. If not, we set db to nullptr and return early.
    if (!check_database(db_name.c_str())) {
        std::cerr << "FATAL: Could not connect to or create database: " << db_name << std::endl;
        return; // Cannot proceed if DB fails to open
    }
    
    // Open the database connection
    int rc = sqlite3_open(db_name.c_str(), &db);
    if (rc) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        db = nullptr;
        return;
    }
    std::cout << "Database connection established to " << db_name << std::endl;

    // Initialize schema
    if (!execute_sql_from_file(people_sql_name.c_str())) {
        std::cerr << "FATAL: Failed to initialize database schema." << std::endl;
        sqlite3_close(db);
        db = nullptr;
        return;
    }
    
    // Ensure mentorship table exists (if not covered by people_sql_name)
    // For robustness, we ensure all schemas are loaded if they weren't implicitly covered.
    // Since the PRD implies all tables exist, we rely on the initial setup.
    // We explicitly load other schemas here to ensure they are present if the initial setup was minimal.
    if (!execute_sql_from_file(mentorship_sql_name.c_str())) {
        std::cerr << "FATAL: Failed to initialize mentorship schema." << std::endl;
        sqlite3_close(db);
        db = nullptr;
        return;
    }
    if (!execute_sql_from_file(school_sql_name.c_str())) {
        std::cerr << "FATAL: Failed to initialize school schema." << std::endl;
        sqlite3_close(db);
        db = nullptr;
        return;
    }
}

// --- Destructor ---

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
        std::cout << "Database connection closed." << std::endl;
    }
}

/**
 * @brief Adds a record to the specified table.
 * @param target The entity type (e.g., "person", "school").
 * @param options Map containing options like -name, -age, etc.
 * @return int Status code (SUCCESS or FAILURE).
 */
int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!db) return Global::DB_OPEN_ERROR;

    std::string sql;
    int rc = SQLITE_OK;

    if (target == "person") {
        // Expected options: -name, -age, -school, -type
        if (options.count("-name") && options.count("-age") && options.count("-school") && options.count("-type")) {
            sql = "INSERT INTO people (name, age, school, type) VALUES (?, ?, ?, ?);";
            
            sqlite3_stmt *stmt;
            rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL preparation error for person add: " << sqlite3_errmsg(db) << std::endl;
                return Global::SQL_EXECUTION_ERROR;
            }

            sqlite3_bind_text(stmt, 1, options.at("-name").c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_int(stmt, 2, std::stoi(options.at("-age")));
            sqlite3_bind_int(stmt, 3, std::stoi(options.at("-school")));
            sqlite3_bind_int(stmt, 4, std::stoi(options.at("-type")));

            rc = sqlite3_step(stmt);
            if (rc != SQLITE_DONE) {
                std::cerr << "Execution error for person add: " << sqlite3_errmsg(db) << std::endl;
                sqlite3_finalize(stmt);
                return Global::SQL_EXECUTION_ERROR;
            }
            sqlite3_finalize(stmt);
            std::cout << "Successfully added new person." << std::endl;
            return Global::SUCCESS;
        }
    } else if (target == "school") {
        // Expected options: -name
        if (options.count("-name")) {
            sql = "INSERT INTO school (name) VALUES (?);";
            
            sqlite3_stmt *stmt;
            rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL preparation error for school add: " << sqlite3_errmsg(db) << std::endl;
                return Global::SQL_EXECUTION_ERROR;
            }

            sqlite3_bind_text(stmt, 1, options.at("-name").c_str(), -1, SQLITE_STATIC);

            rc = sqlite3_step(stmt);
            if (rc != SQLITE_DONE) {
                std::cerr << "Execution error for school add: " << sqlite3_errmsg(db) << std::endl;
                sqlite3_finalize(stmt);
                return Global::SQL_EXECUTION_ERROR;
            }
            sqlite3_finalize(stmt);
            std::cout << "Successfully added new school." << std::endl;
            return Global::SUCCESS;
        }
    }

    if (target == "person") {
        // Check if school exists before adding person
        std::string check_sql = "SELECT ID FROM school WHERE ID = ?;";
        sqlite3_stmt *stmt;
        int rc = sqlite3_prepare_v2(db, check_sql.c_str(), -1, &stmt, 0);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL preparation error for school check: " << sqlite3_errmsg(db) << std::endl;
            return Global::SQL_EXECUTION_ERROR;
        }
        sqlite3_bind_int(stmt, 1, std::stoi(options.at("-school")));
        rc = sqlite3_step(stmt);
        sqlite3_finalize(stmt);

        if (rc != SQLITE_ROW) {
            std::cerr << "Error: School ID " << options.at("-school") << " does not exist." << std::endl;
            return Global::RECORD_NOT_EXISTS;
        }
    }

    std::cerr << "Error: Missing required options for adding " << target << "." << std::endl;
    return Global::NOT_ENOUGH_OPTIONS;
}

/**
 * @brief Deletes a record based on ID.
 * @param target The entity type (e.g., "person", "school").
 * @param options Map containing options, must include -id.
 * @return int Status code (SUCCESS or FAILURE).
 */
int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!db) return Global::DB_OPEN_ERROR;

    if (!options.count("-id")) {
        std::cerr << "Error: -id is compulsory for deletion." << std::endl;
        return Global::NOT_ENOUGH_OPTIONS;
    }

    std::string sql;
    int id = std::stoi(options.at("-id"));

    if (target == "person") {
        sql = "DELETE FROM people WHERE ID = ?;";
    } else if (target == "school") {
        sql = "DELETE FROM school WHERE ID = ?;";
    } else {
        std::cerr << "Error: Unknown target for deletion: " << target << std::endl;
        return Global::INVALID_OPTION;
    }

    sqlite3_stmt *stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL preparation error for delete: " << sqlite3_errmsg(db) << std::endl;
        return Global::SQL_EXECUTION_ERROR;
    }

    sqlite3_bind_int(stmt, 1, id);

    rc = sqlite3_step(stmt);
    if (rc != SQLITE_DONE) {
        std::cerr << "Execution error for delete: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_finalize(stmt);
        return Global::SQL_EXECUTION_ERROR;
    }
    sqlite3_finalize(stmt);

    // Check if any row was affected
    if (sqlite3_changes(db) == 0) {
        std::cout << "Warning: No record found with ID " << id << " in " << target << "." << std::endl;
        return Global::RECORD_NOT_EXISTS;
    }

    std::cout << "Successfully deleted record ID " << id << " from " << target << "." << std::endl;
    return Global::SUCCESS;
}

/**
 * @brief Updates an existing record.
 * @param target The entity type (e.g., "person", "school").
 * @param options Map containing options, must include -id.
 * @return int Status code (SUCCESS or FAILURE).
 */
int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!db) return Global::DB_OPEN_ERROR;

    if (!options.count("-id")) {
        std::cerr << "Error: -id is compulsory for updating." << std::endl;
        return Global::NOT_ENOUGH_OPTIONS;
    }

    std::string sql = "";
    std::vector<std::pair<std::string, std::string>> updates; // {column, value}
    int id = std::stoi(options.at("-id"));
    
    // Collect all fields to update
    if (target == "person") {
        if (options.count("-name")) updates.push_back({"name", options.at("-name")});
        if (options.count("-age")) updates.push_back({"age", options.at("-age")});
        if (options.count("-school")) updates.push_back({"school", options.at("-school")});
        if (options.count("-type")) updates.push_back({"type", options.at("-type")});
    } else if (target == "school") {
        if (options.count("-name")) updates.push_back({"name", options.at("-name")});
    }

    if (updates.empty()) {
        std::cerr << "Error: No fields provided to update for " << target << "." << std::endl;
        return Global::NOT_ENOUGH_OPTIONS;
    }

    // Build SET clause: "col1 = ? , col2 = ?"
    std::string set_clause = "";
    for (size_t i = 0; i < updates.size(); ++i) {
        set_clause += updates[i].first + " = ?";
        if (i < updates.size() - 1) {
            set_clause += ", ";
        }
    }

    // Final SQL: UPDATE table SET col1=?, col2=? WHERE ID=?
    sql = "UPDATE " + target + " SET " + set_clause + " WHERE ID = ?;";

    sqlite3_stmt *stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL preparation error for update: " << sqlite3_errmsg(db) << std::endl;
        return Global::SQL_EXECUTION_ERROR;
    }

    // Bind values for SET clause (1 to N)
    for (size_t i = 0; i < updates.size(); ++i) {
        const std::string& col = updates[i].first;
        const std::string& val = updates[i].second;
        
        if (col == "name") {
            sqlite3_bind_text(stmt, i + 1, val.c_str(), -1, SQLITE_STATIC);
        } else if (col == "age") {
            sqlite3_bind_int(stmt, i + 1, std::stoi(val));
        } else if (col == "school") {
            sqlite3_bind_int(stmt, i + 1, std::stoi(val));
        } else if (col == "type") {
            sqlite3_bind_int(stmt, i + 1, std::stoi(val));
        } else if (col == "name" && target == "school") {
             sqlite3_bind_text(stmt, i + 1, val.c_str(), -1, SQLITE_STATIC);
        }
    }

    // Bind ID (last parameter)
    sqlite3_bind_int(stmt, updates.size() + 1, id);

    rc = sqlite3_step(stmt);
    if (rc != SQLITE_DONE) {
        std::cerr << "Execution error for update: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_finalize(stmt);
        return Global::SQL_EXECUTION_ERROR;
    }
    sqlite3_finalize(stmt);

    // Check if any row was affected
    if (sqlite3_changes(db) == 0) {
        std::cout << "Warning: No record found with ID " << id << " in " << target << " to update." << std::endl;
        return Global::RECORD_NOT_EXISTS;
    }

    std::cout << "Successfully updated record ID " << id << " in " << target << "." << std::endl;
    return Global::SUCCESS;
}

/**
 * @brief Handles mentorship operations (assign and lookup).
 * @param target The mentorship subcommand ("assign" or "lookup").
 * @param options Map containing required IDs.
 * @return int Status code (SUCCESS or FAILURE).
 */
int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!db) return Global::DB_OPEN_ERROR;

    if (target == "assign") {
        // ./UMM mentor assign -student STUDENT_ID -mentor FACULTY_ID
        if (options.count("-student") && options.count("-mentor")) {
            int student_id = std::stoi(options.at("-student"));
            int mentor_id = std::stoi(options.at("-mentor"));

            std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (?, ?);";
            sqlite3_stmt *stmt;
            int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL preparation error for mentor assign: " << sqlite3_errmsg(db) << std::endl;
                return Global::SQL_EXECUTION_ERROR;
            }

            sqlite3_bind_int(stmt, 1, student_id);
            sqlite3_bind_int(stmt, 2, mentor_id);

            rc = sqlite3_step(stmt);
            if (rc != SQLITE_DONE) {
                std::cerr << "Execution error for mentor assign: " << sqlite3_errmsg(db) << std::endl;
                sqlite3_finalize(stmt);
                return Global::SQL_EXECUTION_ERROR;
            }
            sqlite3_finalize(stmt);
            std::cout << "Successfully assigned mentor " << mentor_id << " to student " << student_id << "." << std::endl;
            return Global::SUCCESS;
        } else {
            std::cerr << "Error: Mentor assign requires -student and -mentor." << std::endl;
            return Global::NOT_ENOUGH_OPTIONS;
        }
    } else if (target == "lookup") {
        // Lookup by student
        if (options.count("-student")) {
            int student_id = std::stoi(options.at("-student"));
            std::string sql = "SELECT mentor FROM mentorship WHERE student = ?;";
            sqlite3_stmt *stmt;
            int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0);
            if (rc != SQLITE_OK) {
                std::cerr << "SQL preparation error for mentor lookup (student): " << sqlite3_errmsg(db) << std::endl;
                return Global::SQL_EXECUTION_ERROR;
            }
            sqlite3_bind_int(stmt, 1, student_id);
            
            if (sqlite3_step(stmt) == SQLITE_ROW) {
                int mentor_id = sqlite3_column_int(stmt, 0);
                std::cout << "Student " << student_id << " is mentored by Faculty ID: " << mentor_id << std::endl;
                sqlite3_finalize(stmt);
                return Global::SUCCESS;
            } else {
                std::cout << "No mentor found for Student ID " << student_id << "." << std::endl;
                sqlite3_finalize(stmt);
                return Global::RECORD_NOT_EXISTS;
            }
        } 
        // Lookup by mentor
        else if (options.count("-mentor")) {
            int mentor_id = std::stoi(options.at("-mentor"));
            std::string sql = "SELECT student FROM mentorship WHERE mentor = ?;";
            
            // Use callback to list all students mentored by this faculty
            char* errMsg = nullptr;
            // We pass a specific string to the callback to identify this lookup type
            char* errMsg_exec = nullptr;
            int res = sqlite3_exec(db, sql.c_str(), PeopleManagement::search_callback, (void*)"mentor_lookup", &errMsg_exec);
            
            if (res != SQLITE_OK) {
                std::cerr << "SQL error during mentor lookup: " << errMsg_exec << std::endl;
                sqlite3_free(errMsg_exec);
                return Global::SQL_EXECUTION_ERROR;
            }
            
            // Since we used sqlite3_exec, no need to finalize a statement handle
            std::cout << "Students mentored by Faculty ID " << mentor_id << " listed above." << std::endl;
            return Global::SUCCESS;
        } else {
            std::cerr << "Error: Mentor lookup requires either -student or -mentor." << std::endl;
            return Global::NOT_ENOUGH_OPTIONS;
        }
    }

    std::cerr << "Error: Invalid mentor command or target." << std::endl;
    return Global::INVALID_OPTION;
}

/**
 * @brief Searches for records in the specified table based on options.
 * @param target The entity type (e.g., "person", "school").
 * @param options Map containing search criteria.
 * @return int Status code (SUCCESS or FAILURE).
 */
int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!db) return Global::DB_OPEN_ERROR;

    std::string sql = "";
    std::string where_clause = "";
    std::vector<std::string> conditions;

    // Build WHERE clause based on options
    if (options.count("-name")) {
        where_clause += "name LIKE '%" + options.at("-name") + "%' AND ";
        conditions.push_back("name");
    }
    if (options.count("-age")) {
        where_clause += "age = " + options.at("-age") + " AND ";
        conditions.push_back("age");
    }
    if (options.count("-school")) {
        where_clause += "school = " + options.at("-school") + " AND ";
        conditions.push_back("school");
    }
    if (options.count("-type")) {
        where_clause += "type = " + options.at("-type") + " AND ";
        conditions.push_back("type");
    }

    // Determine table and base query
    if (target == "person") {
        sql = "SELECT * FROM people";
        if (!conditions.empty()) {
            // Remove trailing " AND "
            where_clause = where_clause.substr(0, where_clause.length() - 5);
            sql += " WHERE " + where_clause;
        }
    } else if (target == "school") {
        sql = "SELECT * FROM school";
        if (options.count("-name")) {
            where_clause = "name LIKE '%" + options.at("-name") + "%'";
            sql += " WHERE " + where_clause;
        }
    }
    // Note: Mentorship search is handled separately in mentor()

    if (sql.empty()) {
        std::cerr << "Error: No valid search criteria provided for " << target << "." << std::endl;
        return Global::NOT_ENOUGH_OPTIONS;
    }

    std::cout << "Executing search query: " << sql << std::endl;

    // Execute query using callback
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), PeopleManagement::search_callback, (void*)target.c_str(), &errMsg);

    if (rc != SQLITE_OK) {
        std::cerr << "SQL error during search for " << target << ": " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return Global::SQL_EXECUTION_ERROR;
    }

    std::cout << "Search operation completed for " << target << "." << std::endl;
    return Global::SUCCESS;
}

/**
 * @brief Checks if a string exists within a vector of strings.
 * @param values The vector to search within.
 * @param value The string to search for.
 * @return true if the value is found, false otherwise.
 */
bool Global::contains(const std::vector<std::string>& values, const std::string& value) {
    for (const auto& v : values) {
        if (v == value) {
            return true;
        }
    }
    return false;
}
