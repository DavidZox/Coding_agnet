#include "people_management.h"
#include "common.h"
#include <iostream>
#include <sstream>
#include <sqlite3.h>
#include <map>
#include <vector>

// --- Global Function Implementations ---

namespace Global {
    bool contains(const std::vector<std::string>& values, const std::string value) {
        for (const auto& val : values) {
            if (val == value) {
                return true;
            }
        }
        return false;
    }

    bool validate_options(const std::string& subcommand, const std::string& target) {
        // Check if subcommand is valid
        if (!contains(COMMANDS, subcommand)) {
            return false;
        }

        // Specific validation for targets based on subcommand
        if (subcommand == "add" || subcommand == "search" || subcommand == "delete" || subcommand == "update") {
            if (target.empty() || !contains(TARGETS, target)) {
                return false;
            }
        } else if (subcommand == "mentor") {
            // Mentor command doesn't strictly require a target in the same way, 
            // but we allow it to pass if the subcommand is recognized.
            return true;
        }
        return true;
    }

    std::map<std::string, std::string> build_options(const std::vector<std::string>& args) {
        std::map<std::string, std::string> options;
        for (size_t i = 0; i < args.size(); ++i) {
            std::string arg = args[i];
            if (arg.rfind("-", 0) == 0) { // Starts with '-'
                std::string key = arg.substr(1);
                if (i + 1 < args.size() && args[i+1].rfind("-", 0) != 0) {
                    // Value follows the key
                    options[key] = args[i+1];
                    i++; // Skip the next argument as it was consumed as a value
                } else {
                    // Flag or key without value (though not expected by PRD)
                    options[key] = "";
                }
            }
        }
        return options;
    }

    int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const PeopleManagement& people_management) {
        if (subcommand == "add") {
            if (target == "person") {
                return people_management.add("person", options);
            } else if (target == "school") {
                return people_management.add("school", options);
            }
        } else if (subcommand == "search") {
            if (target == "person" || target == "school") {
                return people_management.search(target, options);
            }
        } else if (subcommand == "delete") {
            if (target == "person" || target == "school") {
                return people_management.delete_record(target, options);
            }
        } else if (subcommand == "update") {
            if (target == "person" || target == "school") {
                return people_management.update(target, options);
            }
        } else if (subcommand == "mentor") {
            // Mentor command uses target as action (assign/lookup)
            if (target == "assign") {
                return people_management.mentor("assign", options);
            } else if (target == "lookup") {
                // We need to distinguish between student lookup and mentor lookup based on options
                if (options.count("student")) {
                    return people_management.mentor("lookup", options); // Student lookup
                } else if (options.count("mentor")) {
                    return people_management.mentor("lookup", options); // Mentor lookup
                }
            }
        }
        return INVALID_OPTION;
    }
}

// Helper function to execute SQL statements that don't return data (INSERT, UPDATE, DELETE, CREATE)
static int execute_sql(sqlite3* db, const std::string& sql) {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), 0, 0, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << errMsg << "\nSQL: " << sql << std::endl;
        sqlite3_free(errMsg);
        return SQL_EXECUTION_ERROR;
    }
    return SUCCESS;
}

// Callback function for SELECT queries
int search_callback(void* data, int argc, char** argv, char** azColName) {
    std::map<std::string, std::string>* results = static_cast<std::map<std::string, std::string>*>(data);
    for (int i = 0; i < argc; i++) {
        std::string col_name = azColName[i];
        std::string value = argv[i] ? argv[i] : "NULL";
        (*results)[col_name] = value;
    }
    return 0; // Return 0 to continue processing rows
}

PeopleManagement::PeopleManagement() : db(nullptr) {
    // Attempt to open the database connection and initialize schema.
    if (!check_database(DB_NAME.c_str())) {
        std::cerr << "Failed to connect or initialize database." << std::endl;
        db = nullptr; 
    } else {
        std::cout << "Database connection established successfully." << std::endl;
    }
}

PeopleManagement::~PeopleManagement() {
    if (db) {
        sqlite3_close(db);
        std::cout << "Database connection closed." << std::endl;
    }
}

// FIX: Changed return type from void to bool to match usage in constructor
bool PeopleManagement::check_database(const char* db_name) {
    // Attempt to open the database connection
    int rc = sqlite3_open(db_name, &db);
    if (rc != SQLITE_OK) {
        std::cerr << "Can't open database: " << sqlite3_errmsg(db) << std::endl;
        db = nullptr;
        return false;
    }

    // Initialize tables if they don't exist
    std::string sql_people = "CREATE TABLE IF NOT EXISTS people ("
                            "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
                            "name TEXT NOT NULL,"
                            "age INTEGER NOT NULL,"
                            "school INTEGER NOT NULL,"
                            "type INTEGER NOT NULL);";
    std::string sql_school = "CREATE TABLE IF NOT EXISTS school ("
                            "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
                            "name TEXT NOT NULL);";
    std::string sql_mentorship = "CREATE TABLE IF NOT EXISTS mentorship ("
                                "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
                                "student INTEGER NOT NULL,"
                                "mentor INTEGER NOT NULL,"
                                "FOREIGN KEY (student) REFERENCES people(ID),"
                                "FOREIGN KEY (mentor) REFERENCES people(ID));";

    // Execute schema creation SQL statements
    if (execute_sql(db, sql_people) != SUCCESS ||
        execute_sql(db, sql_school) != SUCCESS ||
        execute_sql(db, sql_mentorship) != SUCCESS) {
        // If schema creation fails, close the connection and return false
        sqlite3_close(db);
        db = nullptr;
        return false;
    }
    return true;
}

int PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    int success = SQL_EXECUTION_ERROR;

    if (target == "person") {
        // Compulsory options for person: -name, -age, -school, -type
        if (options.count("name") && options.count("age") && options.count("school") && options.count("type")) {
            try {
                int age = std::stoi(options.at("age"));
                int school_id = std::stoi(options.at("school"));
                int type = std::stoi(options.at("type"));

                sql = "INSERT INTO people (name, age, school, type) VALUES (?, ?, ?, ?);";
                sqlite3_stmt* stmt;
                if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) == SQLITE_OK) {
                    sqlite3_bind_text(stmt, 1, options.at("name").c_str(), -1, SQLITE_STATIC);
                    sqlite3_bind_int(stmt, 2, age);
                    sqlite3_bind_int(stmt, 3, school_id);
                    sqlite3_bind_int(stmt, 4, type);
                    if (sqlite3_step(stmt) == SQLITE_DONE) {
                        std::cout << "Successfully added new person." << std::endl;
                        success = SUCCESS;
                    } else {
                        std::cerr << "Execution failed: " << sqlite3_errmsg(db) << std::endl;
                    }
                    sqlite3_finalize(stmt);
                } else {
                    std::cerr << "Failed to prepare statement: " << sqlite3_errmsg(db) << std::endl;
                }
            } catch (const std::exception& e) {
                std::cerr << "Error parsing options: " << e.what() << std::endl;
            }
        } else {
            std::cerr << "Error: Missing compulsory options for adding a person." << std::endl;
        }
    } else if (target == "school") {
        // Compulsory options for school: -name
        if (options.count("name")) {
            sql = "INSERT INTO school (name) VALUES (?);";
            sqlite3_stmt* stmt;
            if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) == SQLITE_OK) {
                sqlite3_bind_text(stmt, 1, options.at("name").c_str(), -1, SQLITE_STATIC);
                if (sqlite3_step(stmt) == SQLITE_DONE) {
                    std::cout << "Successfully added new school." << std::endl;
                    success = SUCCESS;
                } else {
                    std::cerr << "Execution failed: " << sqlite3_errmsg(db) << std::endl;
                }
                sqlite3_finalize(stmt);
            } else {
                std::cerr << "Failed to prepare statement: " << sqlite3_errmsg(db) << std::endl;
            }
        } else {
            std::cerr << "Error: Missing compulsory option for adding a school." << std::endl;
        }
    } else {
        std::cerr << "Error: Unsupported target for add operation." << std::endl;
        return SQL_EXECUTION_ERROR;
    }
    return success;
}

int PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) const {
    std::string sql;
    std::string table_name;
    int rc;

    if (target == "person") {
        table_name = "people";
        // Build WHERE clause dynamically
        std::string where_clause = "";
        std::vector<std::string> conditions;
        std::vector<std::string> values;

        if (options.count("name")) {
            conditions.push_back("name LIKE ?");
            values.push_back("%" + options.at("name") + "%");
        }
        if (options.count("age")) {
            conditions.push_back("age = ?");
            values.push_back(options.at("age"));
        }
        if (options.count("school")) {
            conditions.push_back("school = ?");
            values.push_back(options.at("school"));
        }
        if (options.count("type")) {
            conditions.push_back("type = ?");
            values.push_back(options.at("type"));
        }

        if (!conditions.empty()) {
            where_clause = " WHERE " + conditions[0];
            for (size_t i = 1; i < conditions.size(); ++i) {
                where_clause += " AND " + conditions[i];
            }
        }

        sql = "SELECT * FROM " + table_name + where_clause + ";";
    } else if (target == "school") {
        table_name = "school";
        std::string where_clause = "";
        if (options.count("name")) {
            where_clause = " WHERE name LIKE ?";
        }
        sql = "SELECT * FROM " + table_name + where_clause + ";";
    } else {
        std::cerr << "Error: Unsupported target for search operation." << std::endl;
        return INVALID_OPTION;
    }

    std::map<std::string, std::string> results;
    // Use sqlite3_exec with the correct callback signature
    rc = sqlite3_exec(db, sql.c_str(), search_callback, &results, nullptr);

    if (rc != SQLITE_OK) {
        std::cerr << "SQL error during search: " << sqlite3_errmsg(db) << std::endl;
        return SQL_EXECUTION_ERROR;
    }

    if (results.empty()) {
        std::cout << "No records found for the specified criteria." << std::endl;
        return RECORD_NOT_EXISTS;
    }

    std::cout << "--- Search Results for " << target << " ---" << std::endl;
    // Print headers based on expected structure for simplicity, as dynamic column name retrieval is complex here.
    if (target == "person") {
        std::cout << "ID, Name, Age, School, Type" << std::endl;
    } else if (target == "school") {
        std::cout << "ID, Name" << std::endl;
    }
    // Since the callback aggregates results into a map where keys are column names, 
    // we iterate over the map. This assumes the callback populated it correctly.
    for (const auto& pair : results) {
        // Print all available columns found in the result set
        std::cout << pair.first << ", " << pair.second << std::endl;
    }
    std::cout << "-----------------------------------" << std::endl;
    return SUCCESS;
}

int PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!options.count("id")) {
        std::cerr << "Error: ID is compulsory for deletion." << std::endl;
        return NOT_ENOUGH_OPTIONS;
    }

    std::string id_str = options.at("id");
    std::string sql;
    int rc = SQL_EXECUTION_ERROR;

    if (target == "person") {
        sql = "DELETE FROM people WHERE ID = ?;";
        sqlite3_stmt* stmt;
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) == SQLITE_OK) {
            sqlite3_bind_int(stmt, 1, std::stoi(id_str));
            if (sqlite3_step(stmt) == SQLITE_DONE) {
                if (sqlite3_changes(db) > 0) {
                    std::cout << "Successfully deleted person with ID: " << id_str << std::endl;
                    rc = SUCCESS;
                } else {
                    std::cout << "Record with ID " << id_str << " not found." << std::endl;
                    rc = RECORD_NOT_EXISTS;
                }
            } else {
                std::cerr << "Execution failed: " << sqlite3_errmsg(db) << std::endl;
                rc = SQL_EXECUTION_ERROR;
            }
            sqlite3_finalize(stmt);
        } else {
            std::cerr << "Failed to prepare statement: " << sqlite3_errmsg(db) << std::endl;
            rc = SQL_EXECUTION_ERROR;
        }
    } else if (target == "school") {
        sql = "DELETE FROM school WHERE ID = ?;";
        sqlite3_stmt* stmt;
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) == SQLITE_OK) {
            sqlite3_bind_int(stmt, 1, std::stoi(id_str));
            if (sqlite3_step(stmt) == SQLITE_DONE) {
                if (sqlite3_changes(db) > 0) {
                    std::cout << "Successfully deleted school with ID: " << id_str << std::endl;
                    rc = SUCCESS;
                } else {
                    std::cout << "Record with ID " << id_str << " not found." << std::endl;
                    rc = RECORD_NOT_EXISTS;
                }
            } else {
                std::cerr << "Execution failed: " << sqlite3_errmsg(db) << std::endl;
                rc = SQL_EXECUTION_ERROR;
            }
            sqlite3_finalize(stmt);
        } else {
            std::cerr << "Failed to prepare statement: " << sqlite3_errmsg(db) << std::endl;
            rc = SQL_EXECUTION_ERROR;
        }
    } else {
        std::cerr << "Error: Unsupported target for delete operation." << std::endl;
        return INVALID_OPTION;
    }
    return rc;
}

int PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (!options.count("id")) {
        std::cerr << "Error: ID is compulsory for update." << std::endl;
        return NOT_ENOUGH_OPTIONS;
    }

    std::string id_str = options.at("id");
    std::string set_clause = "";
    std::vector<std::string> updates;
    std::vector<std::string> values;

    // Build SET clause dynamically
    if (target == "person") {
        if (options.count("name")) {
            set_clause += "name = ? ";
            updates.push_back("name");
            values.push_back(options.at("name"));
        }
        if (options.count("age")) {
            set_clause += "age = ? ";
            updates.push_back("age");
            values.push_back(options.at("age"));
        }
        if (options.count("school")) {
            set_clause += "school = ? ";
            updates.push_back("school");
            values.push_back(options.at("school"));
        }
        if (options.count("type")) {
            set_clause += "type = ? ";
            updates.push_back("type");
            values.push_back(options.at("type"));
        }
    } else if (target == "school") {
        if (options.count("name")) {
            set_clause += "name = ? ";
            updates.push_back("name");
            values.push_back(options.at("name"));
        }
    }

    if (set_clause.empty()) {
        std::cerr << "Error: No update options provided." << std::endl;
        return INVALID_OPTION;
    }

    // Construct final SQL
    std::string sql = "UPDATE " + target + " SET " + set_clause + " WHERE ID = ?;";

    sqlite3_stmt* stmt;
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) != SQLITE_OK) {
        std::cerr << "Failed to prepare update statement: " << sqlite3_errmsg(db) << std::endl;
        return SQL_EXECUTION_ERROR;
    }

    // Bind update values
    for (size_t i = 0; i < updates.size(); ++i) {
        int param_index = i + 1;
        std::string& val = values[i];
        if (updates[i] == "name") {
            sqlite3_bind_text(stmt, param_index, val.c_str(), -1, SQLITE_STATIC);
        } else if (updates[i] == "age") {
            sqlite3_bind_int(stmt, param_index, std::stoi(val));
        } else if (updates[i] == "school") {
            sqlite3_bind_int(stmt, param_index, std::stoi(val));
        } else if (updates[i] == "type") {
            sqlite3_bind_int(stmt, param_index, std::stoi(val));
        }
    }

    // Bind ID parameter (always last)
    int id_param_index = updates.size() + 1;
    sqlite3_bind_int(stmt, id_param_index, std::stoi(id_str));

    if (sqlite3_step(stmt) == SQLITE_DONE) {
        if (sqlite3_changes(db) > 0) {
            std::cout << "Successfully updated record with ID: " << id_str << std::endl;
            sqlite3_finalize(stmt);
            return SUCCESS;
        } else {
            std::cout << "Record with ID " << id_str << " not found for update." << std::endl;
            sqlite3_finalize(stmt);
            return RECORD_NOT_EXISTS;
        }
    } else {
        std::cerr << "Update execution failed: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_finalize(stmt);
        return SQL_EXECUTION_ERROR;
    }
}

int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const {
    if (target == "assign" && options.count("student") && options.count("mentor")) {
        std::string student_id = options.at("student");
        std::string mentor_id = options.at("mentor");

        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (?, ?);";
        sqlite3_stmt* stmt;
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) == SQLITE_OK) {
            sqlite3_bind_int(stmt, 1, std::stoi(student_id));
            sqlite3_bind_int(stmt, 2, std::stoi(mentor_id));
            if (sqlite3_step(stmt) == SQLITE_DONE) {
                std::cout << "Successfully assigned mentor." << std::endl;
                sqlite3_finalize(stmt);
                return SUCCESS;
            } else {
                std::cerr << "Mentor assignment failed: " << sqlite3_errmsg(db) << std::endl;
                sqlite3_finalize(stmt);
                return SQL_EXECUTION_ERROR;
            }
        } else {
            std::cerr << "Failed to prepare mentor assignment statement: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }
    } else if (target == "lookup" && options.count("student")) {
        std::string student_id_str = options.at("student");
        std::string sql = "SELECT mentor FROM mentorship WHERE student = ?;";
        sqlite3_stmt* stmt;
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) == SQLITE_OK) {
            sqlite3_bind_int(stmt, 1, std::stoi(student_id_str));
            if (sqlite3_step(stmt) == SQLITE_ROW) {
                int mentor_id = sqlite3_column_int(stmt, 0);
                std::cout << "Mentor ID for student " << student_id_str << " is: " << mentor_id << std::endl;
                sqlite3_finalize(stmt);
                return SUCCESS;
            } else {
                std::cout << "No mentor found for student ID: " << student_id_str << std::endl;
                sqlite3_finalize(stmt);
                return RECORD_NOT_EXISTS;
            }
        } else {
            std::cerr << "Failed to prepare student lookup statement: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }
    } else if (target == "lookup" && options.count("mentor")) {
        std::string mentor_id_str = options.at("mentor");
        std::string sql = "SELECT student FROM mentorship WHERE mentor = ?;";
        sqlite3_stmt* stmt;
        if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, 0) == SQLITE_OK) {
            sqlite3_bind_int(stmt, 1, std::stoi(mentor_id_str));
            int count = 0;
            while (sqlite3_step(stmt) == SQLITE_ROW) {
                int student_id = sqlite3_column_int(stmt, 0);
                std::cout << "Student mentored by ID " << mentor_id_str << " is: " << student_id << std::endl;
                count++;
            }
            if (count == 0) {
                std::cout << "No students found mentored by faculty ID: " << mentor_id_str << std::endl;
            }
            sqlite3_finalize(stmt);
            return SUCCESS;
        } else {
            std::cerr << "Failed to prepare mentor lookup statement: " << sqlite3_errmsg(db) << std::endl;
            return SQL_EXECUTION_ERROR;
        }
    } else {
        std::cerr << "Error: Invalid mentor operation or missing required options." << std::endl;
        return INVALID_OPTION;
    }
}
