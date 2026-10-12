#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>

inline const std::string db_name = "umm.db";
inline const std::string people_sql_name = "sql/people.sql";
inline const std::string mentorship_sql_name = "sql/mentorship.sql";
inline const std::string school_sql_name = "sql/school.sql";

inline const std::vector<std::string> columns = {"id", "name", "age", "school", "type"};
inline const std::vector<std::string> full_columns = {"id", "name", "age", "school", "type"};
inline const std::vector<std::string> commands = {"add", "search", "delete", "mentor", "update"};
inline const std::vector<std::string> targets = {"person", "school"};

// Status codes
inline const int SUCCESS = 0;
inline const int DB_OPEN_ERROR = 1;
inline const int INVALID_OPTION = 2;
inline const int NOT_ENOUGH_OPTIONS = 3;
inline const int RECORD_NOT_EXISTS = 4;
inline const int SQL_EXECUTION_ERROR = 5;
inline const int FAILURE = 6;

#endif // COMMON_H
