#ifndef COMMON_H
#define COMMON_H

// Status codes
inline const int SUCCESS = 0;
inline const int DB_OPEN_ERROR = 1;
inline const int INVALID_OPTION = 2;
inline const int NOT_ENOUGH_OPTIONS = 3;
inline const int RECORD_NOT_EXISTS = 4;
inline const int SQL_EXECUTION_ERROR = 5;
inline const int FAILURE = 6;

// Database paths and schema files
inline const char* db_name = "umm.db";
inline const char* people_sql_name = "sql/people.sql";
inline const char* mentorship_sql_name = "sql/mentorship.sql";
inline const char* school_sql_name = "sql/school.sql";

// Commands and targets
// Note: Using raw arrays to avoid dependency on <vector> and <string> if environment is broken
inline const char* commands[] = {"add", "search", "delete", "mentor", "update"};
inline const int commands_size = 5;

inline const char* targets[] = {"person", "school"};
inline const int targets_size = 2;

// Column names
inline const char* columns[] = {"name", "age", "school", "type", "id", "student", "mentor"};
inline const int columns_size = 7;

inline const char* full_columns[] = {"ID", "name", "age", "school", "type", "student", "mentor"};
inline const int full_columns_size = 7;

#endif // COMMON_H
