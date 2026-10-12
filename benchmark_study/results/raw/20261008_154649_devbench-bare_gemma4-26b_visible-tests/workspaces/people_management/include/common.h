#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>

// Status codes
const int SUCCESS = 0;
const int DB_OPEN_ERROR = 1;
const int INVALID_OPTION = 2;
const int NOT_ENOUGH_OPTIONS = 3;
const int RECORD_NOT_EXISTS = 4;
const int SQL_EXECUTION_ERROR = 5;
const int FAILURE = 6;

// Database configuration
const char* db_name = "database.sqlite3";
const char* people_sql_name = "sql/people.sql";
const char* mentorship_sql_name = "sql/mentorship.sql";
const char* school_sql_name = "sql/school.sql";

// Column names and table targets
const std::vector<std::string> columns = {"id", "name", "age", "school", "type"};
const std::vector<std::string> full_columns = {"id", "name", "age", "school", "type"};
const std::vector<std::string> commands = {"add", "search", "delete", "mentor", "update"};
const std::vector<std::string> targets = {"person", "school"};

#endif // COMMON_H
