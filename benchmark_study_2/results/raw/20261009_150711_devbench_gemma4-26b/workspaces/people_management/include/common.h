#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>

namespace Global {
    // Status codes
    const int SUCCESS = 0;
    const int DB_OPEN_ERROR = 1;
    const int INVALID_OPTION = 2;
    const int NOT_ENOUGH_OPTIONS = 3;
    const int RECORD_NOT_EXISTS = 4;
    const int SQL_EXECUTION_ERROR = 5;
    const int FAILURE = 6;

    // Commands
    const std::vector<std::string> commands = {"add", "search", "delete", "mentor", "update"};

    // Targets
    const std::vector<std::string> targets = {"person", "school"};

    // Columns
    const std::vector<std::string> columns = {"id", "name", "age", "school", "type", "student", "mentor"};
    const std::vector<std::string> full_columns = {"id", "name", "age", "school", "type", "student", "mentor"};

    // Database paths and SQL files
    const std::string db_name = "umm.db";
    const std::string people_sql_name = "sql/people.sql";
    const std::string mentorship_sql_name = "sql/mentorship.sql";
    const std::string school_sql_name = "sql/school.sql";
}

#endif // COMMON_H
