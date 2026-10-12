#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>

// Constants
const std::vector<std::string> columns = {"ID", "name", "age", "school", "type"};
const std::vector<std::string> full_columns = {"ID", "name", "age", "school", "type", "student", "mentor"};
const std::vector<std::string> commands = {"add", "search", "delete", "update", "mentor"};
const std::vector<std::string> targets = {"person", "school"};

// Database scheme file paths
const std::string people_sql_name = "../sql/people.sql";
const std::string mentorship_sql_name = "../sql/mentorship.sql";
const std::string school_sql_name = "../sql/school.sql";

// Database path
const std::string db_name = "university.db";

// Status codes
const int SUCCESS = 0;
const int DB_OPEN_ERROR = 1;
const int INVALID_OPTION = 2;
const int NOT_ENOUGH_OPTIONS = 3;
const int RECORD_NOT_EXISTS = 4;
const int SQL_EXECUTION_ERROR = 5;
const int FAILURE = 6;

// Function declarations
std::map<std::string, std::string> build_options(const std::vector<std::string>& args);

#endif // COMMON_H
