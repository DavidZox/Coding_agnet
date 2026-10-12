#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>

// --- Database File Paths ---
const std::string people_sql_name = "sql/people.sql";
const std::string mentorship_sql_name = "sql/mentorship.sql";
const std::string school_sql_name = "sql/school.sql";
const std::string db_name = "university_management.db";

// --- Command and Target Definitions ---
// Commands: add, search, delete, mentor, update
const std::vector<std::string> commands = {"add", "search", "delete", "mentor", "update"};

// Targets: person, school
const std::vector<std::string> targets = {"person", "school"};

// Columns/Fields (used for options/data)
// People: ID, name, age, school, type
const std::vector<std::string> people_columns = {"ID", "name", "age", "school", "type"};
const std::vector<std::string> full_people_columns = {"ID", "name", "age", "school", "type"};

// School: ID, name
const std::vector<std::string> school_columns = {"ID", "name"};
const std::vector<std::string> full_school_columns = {"ID", "name"};

// Mentorship: ID, student, mentor
const std::vector<std::string> mentorship_columns = {"ID", "student", "mentor"};
const std::vector<std::string> full_mentorship_columns = {"ID", "student", "mentor"};


// --- Status Codes ---
const int SUCCESS = 0;
const int DB_OPEN_ERROR = 1;
const int INVALID_OPTION = 2;
const int NOT_ENOUGH_OPTIONS = 3;
const int RECORD_NOT_EXISTS = 4;
const int SQL_EXECUTION_ERROR = 5;
const int FAILURE = 6;

#endif // COMMON_H
