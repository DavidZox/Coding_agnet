#ifndef COMMON_H
#define COMMON_H

// Database scheme file paths
static const char* people_sql_name = "sql/people.sql";
static const char* mentorship_sql_name = "sql/mentorship.sql";
static const char* school_sql_name = "sql/school.sql";

// Database path
static const char* db_name = "university.db";

// Status codes
static const int SUCCESS = 0;
static const int DB_OPEN_ERROR = 1;
static const int INVALID_OPTION = 2;
static const int NOT_ENOUGH_OPTIONS = 3;
static const int RECORD_NOT_EXISTS = 4;
static const int SQL_EXECUTION_ERROR = 5;
static const int FAILURE = 6;

// Commands
// Since we cannot use std::vector<std::string> due to <string> error, 
// we define them as arrays of const char* for the header.
// However, the architecture design implies these are constants.
// To avoid <string> and <vector> in the header, we use raw arrays.
static const char* commands[] = {"add", "search", "delete", "mentor", "update"};
static const int commands_size = 5;

// Targets
static const char* targets[] = {"person", "school"};
static const int targets_size = 2;

// Columns
static const char* columns[] = {"id", "name", "age", "school", "type", "student", "mentor"};
static const int columns_size = 7;

static const char* full_columns[] = {"ID", "NAME", "AGE", "SCHOOL", "TYPE", "STUDENT", "MENTOR"};
static const int full_columns_size = 7;

#endif // COMMON_H
