#include "people_management.h"
#include <sqlite3.h>
#include <iostream>
#include <map>
#include <string>

PeopleManagement::PeopleManagement() {
    db = nullptr;
    const char* db_name = "university.db";
    int rc = sqlite3_open(db_name, &db);
    if (rc != SQLITE_OK) {
        std::cerr << "Cannot open database: " << sqlite3_errmsg(db) << std::endl;
        sqlite3_close(db);
        db = nullptr;
    } else {
        check_database(db_name);
    }
}

void PeopleManagement::check_database(const char* db_name) {
    execute_sql_from_file("sql/people.sql");
    execute_sql_from_file("sql/mentorship.sql");
    execute_sql_from_file("sql/school.sql");
}

PeopleManagement::~PeopleManagement() {
    if (db != nullptr) {
        sqlite3_close(db);
    }
}

void PeopleManagement::check_database(const char* db_name) {
    execute_sql_from_file("sql/people.sql");
    execute_sql_from_file("sql/mentorship.sql");
    execute_sql_from_file("sql/school.sql");
}

void PeopleManagement::execute_sql_from_file(const char* file_name) const {
    std::ifstream sqlFile(file_name);
    if (!sqlFile.is_open()) {
        std::cerr << "Cannot open SQL file: " << file_name << std::endl;
        return;
    }

    std::string sql((std::istreambuf_iterator<char>(sqlFile)), std::istreambuf_iterator<char>());
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << errMsg << std::endl;
        sqlite3_free(errMsg);
    }
}

int PeopleManagement::search_callback(void *data, int argc, char **argv, char **azColName) {
    for (int i = 0; i < argc; i++) {
        std::cout << azColName[i] << " = " << (argv[i] ? argv[i] : "NULL") << std::endl;
    }
    std::cout << std::endl;
    return 0;
}

void PeopleManagement::add(const std::string& target, const std::map<std::string, std::string>& options) {
    if (target == "person") {
        std::string name = options.at("name");
        int age = std::stoi(options.at("age"));
        int school = std::stoi(options.at("school"));
        int type = std::stoi(options.at("type"));

        std::string sql = "INSERT INTO people (name, age, school, type) VALUES (?, ?, ?, ?);";
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
            return;
        }

        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 2, age);
        sqlite3_bind_int(stmt, 3, school);
        sqlite3_bind_int(stmt, 4, type);

        rc = sqlite3_step(stmt);
        if (rc != SQLITE_DONE) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        }

        sqlite3_finalize(stmt);
    } else if (target == "school") {
        std::string name = options.at("name");

        std::string sql = "INSERT INTO school (name) VALUES (?);";
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
            return;
        }

        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_STATIC);

        rc = sqlite3_step(stmt);
        if (rc != SQLITE_DONE) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        }

        sqlite3_finalize(stmt);
    }
}

void PeopleManagement::search(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql;
    if (target == "person") {
        sql = "SELECT * FROM people WHERE 1=1";
        for (const auto& option : options) {
            if (option.first == "name") {
                sql += " AND name = ?";
            } else if (option.first == "age") {
                sql += " AND age = ?";
            } else if (option.first == "school") {
                sql += " AND school = ?";
            } else if (option.first == "type") {
                sql += " AND type = ?";
            }
        }
    } else if (target == "school") {
        sql = "SELECT * FROM school WHERE 1=1";
        for (const auto& option : options) {
            if (option.first == "name") {
                sql += " AND name = ?";
            }
        }
    }

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        return;
    }

    int index = 1;
    for (const auto& option : options) {
        if (option.first == "name") {
            sqlite3_bind_text(stmt, index, option.second.c_str(), -1, SQLITE_STATIC);
        } else if (option.first == "age" || option.first == "school" || option.first == "type") {
            sqlite3_bind_int(stmt, index, std::stoi(option.second));
        }
        index++;
    }

    rc = sqlite3_step(stmt);
    while (rc == SQLITE_ROW) {
        search_callback(nullptr, sqlite3_column_count(stmt), sqlite3_column_text(stmt, 0), sqlite3_column_name(stmt));
        rc = sqlite3_step(stmt);
    }

    if (rc != SQLITE_DONE) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
    }

    sqlite3_finalize(stmt);
}

void PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) {
    if (target == "assign") {
        int student_id = std::stoi(options.at("student"));
        int mentor_id = std::stoi(options.at("mentor"));

        std::string sql = "INSERT INTO mentorship (student, mentor) VALUES (?, ?);";
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
            return;
        }

        sqlite3_bind_int(stmt, 1, student_id);
        sqlite3_bind_int(stmt, 2, mentor_id);

        rc = sqlite3_step(stmt);
        if (rc != SQLITE_DONE) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        }

        sqlite3_finalize(stmt);
    } else if (target == "lookup") {
        std::string sql;
        if (options.find("student") != options.end()) {
            sql = "SELECT mentor FROM mentorship WHERE student = ?;";
        } else if (options.find("mentor") != options.end()) {
            sql = "SELECT student FROM mentorship WHERE mentor = ?;";
        } else {
            std::cerr << "Invalid options for mentor lookup." << std::endl;
            return;
        }

        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
            return;
        }

        int id = std::stoi(options.find("student") != options.end() ? options.at("student") : options.at("mentor"));
        sqlite3_bind_int(stmt, 1, id);

        rc = sqlite3_step(stmt);
        if (rc == SQLITE_ROW) {
            std::cout << "ID = " << sqlite3_column_int(stmt, 0) << std::endl;
        } else if (rc != SQLITE_DONE) {
            std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        }

        sqlite3_finalize(stmt);
    }
}

void PeopleManagement::delete_record(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql;
    if (target == "person" || target == "school") {
        sql = "DELETE FROM " + target + " WHERE id = ?";
    } else {
        std::cerr << "Invalid target for delete operation." << std::endl;
        return;
    }

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        return;
    }

    int id = std::stoi(options.at("id"));
    sqlite3_bind_int(stmt, 1, id);

    rc = sqlite3_step(stmt);
    if (rc != SQLITE_DONE) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
    }

    sqlite3_finalize(stmt);
}

void PeopleManagement::update(const std::string& target, const std::map<std::string, std::string>& options) {
    std::string sql;
    if (target == "person") {
        sql = "UPDATE people SET ";
        bool first = true;
        for (const auto& option : options) {
            if (option.first == "name") {
                if (!first) sql += ", ";
                sql += "name = ?";
                first = false;
            } else if (option.first == "age") {
                if (!first) sql += ", ";
                sql += "age = ?";
                first = false;
            } else if (option.first == "school") {
                if (!first) sql += ", ";
                sql += "school = ?";
                first = false;
            } else if (option.first == "type") {
                if (!first) sql += ", ";
                sql += "type = ?";
                first = false;
            }
        }
        sql += " WHERE id = ?";
    } else if (target == "school") {
        sql = "UPDATE school SET ";
        bool first = true;
        for (const auto& option : options) {
            if (option.first == "name") {
                if (!first) sql += ", ";
                sql += "name = ?";
                first = false;
            }
        }
        sql += " WHERE id = ?";
    } else {
        std::cerr << "Invalid target for update operation." << std::endl;
        return;
    }

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
        return;
    }

    int index = 1;
    for (const auto& option : options) {
        if (option.first == "name") {
            sqlite3_bind_text(stmt, index, option.second.c_str(), -1, SQLITE_STATIC);
        } else if (option.first == "age" || option.first == "school" || option.first == "type") {
            sqlite3_bind_int(stmt, index, std::stoi(option.second));
        }
        index++;
    }

    int id = std::stoi(options.at("id"));
    sqlite3_bind_int(stmt, index, id);

    rc = sqlite3_step(stmt);
    if (rc != SQLITE_DONE) {
        std::cerr << "SQL error: " << sqlite3_errmsg(db) << std::endl;
    }

    sqlite3_finalize(stmt);
}
