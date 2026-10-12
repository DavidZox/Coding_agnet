#include "people_management.h"
#include "utils.h"
#include <iostream>
#include <sstream>

// --- Private Helper Implementations ---

/**
 * @brief Internal helper to check the result of an SQL execution.
 * @param sql The SQL statement executed.
 * @return true if execution was successful, false otherwise.
 */
bool PeopleManagement::check_select(const std::string& sql) const {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, 0, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error in SELECT: " << errMsg << "\nSQL: " << sql << std::endl;
        sqlite3_free(errMsg);
        return false;
    }
    return true;
}

/**
 * @brief Initializes the database connection and creates necessary tables if they don't exist.
 * @param db_name The name of the SQLite database file.
 * @return true if the database connection and schema setup were successful, false otherwise.
 */
bool PeopleManagement::check_database(const char* db_name) const {
    int rc = sqlite3_open(db_name, &db);
    if (rc) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }
    return true;
}

/**
 * @brief Executes an SQL statement read from a file.
 * @param file_name The path to the SQL schema file.
 * @return true if the execution was successful, false otherwise.
 */
bool PeopleManagement::execute_sql_from_file(const char* file_name) const {
    FILE* fp = fopen(file_name, "r");
    if (!fp) {
        std::cerr << "Error: Could not open SQL file: " << file_name << std::endl;
        return false;
    }

    char buffer[1024];
    bool success = true;

    while (fgets(buffer, sizeof(buffer), fp) != nullptr) {
        std::string sql(buffer);
        // Remove potential newline characters
        if (!sql.empty() && sql.back() == '\n') {
            sql.pop_back();
        }
        
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db, sql.c_str(), nullptr, 0, &errMsg);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL error executing file " << file_name << ": " << errMsg << "\nSQL: " << sql << std::endl;
            sqlite3_free(errMsg);
            success = false;
            break;
        }
    }

    fclose(fp);
    return success;
}

/**
 * @brief Callback function used by sqlite3_exec for SELECT operations.
 * Prints results to stdout in a readable format.
 */
void PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    std::cout << "| ";
    for (int i = 0; i < argc; i++) {
        std::cout << (argv[i] ? argv[i] : "NULL") << " | ";
    }
    std::cout << "|\n";
}

// --- Public Interface Implementations ---

/**
 * @brief Constructor: Opens the database and initializes the schema.
 * @param db_name The name of the database file.
 * @return true if the database connection and schema setup were successful, false otherwise.
 */
PeopleManagement::PeopleManagement(const std::string& db_name) : db(nullptr) {
    if (!check_database(db_name.c_str())) {
        // db is null or connection failed, handle error state if necessary
        return;
    }

    // Initialize schemas
    if (!execute_sql_from_file(people_sql_name.c_str())) {
        sqlite3_close(db);
        db = nullptr;
        return;
    }
    if (!execute_sql_from_file(school_sql_name.c_str())) {
        sqlite3_close(db);
        db = nullptr;
        return;
    }
    if (!execute_sql_from_file(mentorship_sql_name.c_str())) {
        sqlite3_close(db);
        db = nullptr;
        return;
    }
}

/**
 * @brief Destructor: Closes the database connection.
 */
PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
    }
}

/**
 * @brief Adds a new record to the database (person or school).
 * @param target The entity type ("person" or "school").
 * @param options A map containing the data fields for the new record.
 * @return The status code of the operation (SUCCESS or SQL_EXECUTION_ERROR).
 */
int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    std::string insert_sql;
    std::string values_str;
    
    if (target == "person") {
        // Expected options: -name, -age, -school, -type
        std::string name = options.count("-name") ? options.at("-name") : "";
        std::string age = options.count("-age") ? options.at("-age") : "";
        std::string school = options.count("-school") ? options.at("-school") : "";
        std::string type = options.count("-type") ? options.at("-type") : "";

        if (name.empty() || age.empty() || school.empty() || type.empty()) {
            std::cerr << "Error: Missing compulsory options for adding a person." << std::endl;
            return SQL_EXECUTION_ERROR;
        }

        insert_sql = "INSERT INTO people (name, age, school, type) VALUES (?, ?, ?, ?);";
        
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, insert_sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "Failed to prepare statement for person: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }

        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 2, std::stoi(age));
        sqlite3_bind_int(stmt, 3, std::stoi(school));
        sqlite3_bind_int(stmt, 4, std::stoi(type));

        rc = sqlite3_step(stmt);
        sqlite3_finalize(stmt);

        if (rc == SQLITE_DONE) {
            std::cout << "Success: Person added successfully." << std::endl;
            return SUCCESS;
        } else {
            std::cerr << "Error adding person: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }

    } else if (target == "school") {
        // Expected options: -name
        std::string name = options.count("-name") ? options.at("-name") : "";

        if (name.empty()) {
            std::cerr << "Error: Missing compulsory option for adding a school." << std::endl;
            return SQL_EXECUTION_ERROR;
        }

        insert_sql = "INSERT INTO school (name) VALUES (?);";
        
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, insert_sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "Failed to prepare statement for school: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }

        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_STATIC);

        rc = sqlite3_step(stmt);
        sqlite3_finalize(stmt);

        if (rc == SQLITE_DONE) {
            std::cout << "Success: School added successfully." << std::endl;
            return SUCCESS;
        } else {
            std::cerr << "Error adding school: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }
    }
    return FAILURE;
}

/**
 * @brief Searches for records based on provided options.
 * @param target The entity type ("person" or "school").
 * @param options A map containing search criteria (e.g., name, age).
 * @return The status code of the operation (SUCCESS or SQL_EXECUTION_ERROR).
 */
int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql_base;
    std::string where_clause = "";
    std::vector<std::pair<std::string, std::string>> conditions;

    if (target == "person") {
        sql_base = "SELECT * FROM people WHERE 1=1";
        
        if (options.count("-name")) {
            where_clause += " AND name LIKE '%" + options.at("-name") + "%'";
            conditions.push_back({"name", options.at("-name")});
        }
        if (options.count("-age")) {
            where_clause += " AND age = " + options.at("-age");
            conditions.push_back({"age", options.at("-age")});
        }
        if (options.count("-school")) {
            where_clause += " AND school = " + options.at("-school");
            conditions.push_back({"school", options.at("-school")});
        }
        if (options.count("-type")) {
            where_clause += " AND type = " + options.at("-type");
            conditions.push_back({"type", options.at("-type")});
        }

    } else if (target == "school") {
        sql_base = "SELECT * FROM school WHERE 1=1";
        
        if (options.count("-name")) {
            where_clause += " AND name LIKE '%" + options.at("-name") + "%'";
            conditions.push_back({"name", options.at("-name")});
        }
    } else {
        std::cerr << "Error: Unknown target for search." << std::endl;
        return FAILURE;
    }

    std::string final_sql = sql_base + where_clause;
    std::cout << "\n--- Search Results for " << target << " ---\n";
    std::cout << "Columns: ID | Name | Age | School | Type\n";
    std::cout << "------------------------------------------\n";

    // Execute the query using the callback function
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, final_sql.c_str(), search_callback, nullptr, &errMsg);

    if (rc != SQLITE_OK) {
        std::cerr << "SQL error during search: " << errMsg << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    
    std::cout << "------------------------------------------\n";
    return SUCCESS;
}

/**
 * @brief Deletes a record based on its ID.
 * @param target The entity type ("person" or "school").
 * @param options A map containing the ID to delete (must contain "-id").
 * @return The status code of the operation (SUCCESS or RECORD_NOT_EXISTS).
 */
int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!options.count("-id")) {
        std::cerr << "Error: Deletion requires a compulsory '-id' option." << std::endl;
        return NOT_ENOUGH_OPTIONS;
    }

    std::string id_str = options.at("-id");
    std::string sql;
    
    if (target == "person") {
        sql = "DELETE FROM people WHERE ID = ?;";
    } else if (target == "school") {
        sql = "DELETE FROM school WHERE ID = ?;";
    } else {
        std::cerr << "Error: Unknown target for deletion." << std::endl;
        return FAILURE;
    }

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        std::cerr << "Failed to prepare statement for deletion: " << sqlite3_errmsg(db) << std::endl;
        return SQL_EXECUTION_ERROR;
    }

    sqlite3_bind_int(stmt, 1, std::stoi(id_str));

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    if (rc == SQLITE_DONE) {
        // Check if any row was actually deleted
        int changes = sqlite3_changes(db);
        if (changes > 0) {
            std::cout << "Success: Record ID " << id_str << " deleted successfully from " << target << "." << std::endl;
            return SUCCESS;
        } else {
            std::cout << "Warning: No record found with ID " << id_str << " in " << target << "." << std::endl;
            return RECORD_NOT_EXISTS;
        }
    } else {
        std::cerr << "Error deleting record: " << sqlite3_errmsg(db) << std::endl;
        return SQL_EXECUTION_ERROR;
    }
}

/**
 * @brief Updates an existing record based on its ID and provided options.
 * @param target The entity type ("person" or "school").
 * @param options A map containing the ID and fields to update.
 * @return The status code of the operation (SUCCESS or RECORD_NOT_EXISTS).
 */
int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!options.count("-id")) {
        std::cerr << "Error: Update requires a compulsory '-id' option." << std::endl;
        return NOT_ENOUGH_OPTIONS;
    }

    std::string id_str = options.at("-id");
    std::string set_clauses;
    std::vector<std::string> values_to_bind;
    int bind_index = 1;

    // Build SET clauses dynamically
    if (target == "person") {
        if (options.count("-name")) {
            set_clauses += "name = ? ";
            values_to_bind.push_back(options.at("-name"));
        }
        if (options.count("-age")) {
            set_clauses += "age = ? ";
            values_to_bind.push_back(options.at("-age"));
        }
        if (options.count("-school")) {
            set_clauses += "school = ? ";
            values_to_bind.push_back(options.at("-school"));
        }
        if (options.count("-type")) {
            set_clauses += "type = ? ";
            values_to_bind.push_back(options.at("-type"));
        }
    } else if (target == "school") {
        if (options.count("-name")) {
            set_clauses += "name = ? ";
            values_to_bind.push_back(options.at("-name"));
        }
    }

    if (set_clauses.empty()) {
        std::cerr << "Error: No fields provided to update for " << target << "." << std::endl;
        return SQL_EXECUTION_ERROR;
    }

    // Append the ID condition
    std::string sql = "UPDATE " + target + " SET " + set_clauses + " WHERE ID = ?;";
    
    // Add ID to the end of bindings
    values_to_bind.push_back(id_str);

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        std::cerr << "Failed to prepare statement for update: " << sqlite3_errmsg(db) << std::endl;
        return SQL_EXECUTION_ERROR;
    }

    // Bind values
    for (size_t i = 0; i < values_to_bind.size(); ++i) {
        int col_idx = i + 1;
        const std::string& val = values_to_bind[i];
        
        if (target == "person" && (i == 1 || i == 2 || i == 3 || i == 4)) { // Name, Age, School, Type
            if (i == 1) sqlite3_bind_text(stmt, col_idx, val.c_str(), -1, SQLITE_STATIC);
            else if (i == 2) sqlite3_bind_int(stmt, col_idx, std::stoi(val));
            else if (i == 3) sqlite3_bind_int(stmt, col_idx, std::stoi(val));
            else if (i == 4) sqlite3_bind_int(stmt, col_idx, std::stoi(val));
        } else if (target == "school" && i == 0) { // Name
            sqlite3_bind_text(stmt, col_idx, val.c_str(), -1, SQLITE_STATIC);
        } else { // ID binding (always last)
            sqlite3_bind_int(stmt, col_idx, std::stoi(val));
        }
    }

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    if (rc == SQLITE_DONE) {
        int changes = sqlite3_changes(db);
        if (changes > 0) {
            std::cout << "Success: Record ID " << id_str << " updated successfully in " << target << "." << std::endl;
            return SUCCESS;
        } else {
            std::cout << "Warning: No record found with ID " << id_str << " in " << target << " to update." << std::endl;
            return RECORD_NOT_EXISTS;
        }
    } else {
        std::cerr << "Error updating record: " << sqlite3_errmsg(db) << std::endl;
        return SQL_EXECUTION_ERROR;
    }
}

/**
 * @brief Handles mentorship operations (assign or lookup).
 * @param target The mentorship action ("assign" or "lookup").
 * @param options A map containing necessary IDs (e.g., -student, -mentor).
 * @return The status code of the operation (SUCCESS or SQL_EXECUTION_ERROR).
 */
int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign") {
        if (!options.count("-student") || !options.count("-mentor")) {
            std::cerr << "Error: Mentor assign requires -student and -mentor IDs." << std::endl;
            return NOT_ENOUGH_OPTIONS;
        }
        std::string student_id = options.at("-student");
        std::string faculty_id = options.at("-mentor");

        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (?, ?);";
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "Failed to prepare statement for mentor assign: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }

        sqlite3_bind_int(stmt, 1, std::stoi(student_id));
        sqlite3_bind_int(stmt, 2, std::stoi(faculty_id));

        rc = sqlite3_step(stmt);
        sqlite3_finalize(stmt);

        if (rc == SQLITE_DONE) {
            std::cout << "Success: Mentorship assigned successfully (Student ID: " << student_id << ", Faculty ID: " << faculty_id << ")." << std::endl;
            return SUCCESS;
        } else {
            std::cerr << "Error assigning mentorship: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }

    } else if (target == "lookup") {
        if (!options.count("-student") && !options.count("-mentor")) {
            std::cerr << "Error: Mentor lookup requires either -student or -mentor ID." << std::endl;
            return NOT_ENOUGH_OPTIONS;
        }

        std::string sql;
        std::string query_type;

        if (options.count("-student")) {
            sql = "SELECT mentor FROM mentorship WHERE student = ?;";
            query_type = "Student";
        } else { // Must be -mentor
            sql = "SELECT student FROM mentorship WHERE mentor = ?;";
            query_type = "Mentor";
        }

        std::cout << "\n--- Mentor Lookup for " << query_type << " ---\n";
        
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "Failed to prepare statement for mentor lookup: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }

        if (options.count("-student")) {
            sqlite3_bind_int(stmt, 1, std::stoi(options.at("-student")));
        } else {
            sqlite3_bind_int(stmt, 1, std::stoi(options.at("-mentor")));
        }

        rc = sqlite3_step(stmt);
        
        if (rc == SQLITE_ROW) {
            int result_id = sqlite3_column_int(stmt, 0);
            std::cout << "Result: Found ID " << result_id << ".\n";
            sqlite3_finalize(stmt);
            return SUCCESS;
        } else {
            std::cout << "Result: No mentorship relation found for the given ID.\n";
            sqlite3_finalize(stmt);
            return RECORD_NOT_EXISTS;
        }
    }
    return FAILURE;
}
