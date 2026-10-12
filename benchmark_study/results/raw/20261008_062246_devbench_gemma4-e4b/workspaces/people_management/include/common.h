#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>

// --- Constants ---

// Database table columns/fields (as described in PRD/SQL files)
// People Table: ID, name, age, school, type
// Mentorship Table: ID, student, mentor
// School Table: ID, name
const std::vector<std::string> PEOPLE_COLUMNS = {"ID", "name", "age", "school", "type"};
const std::vector<std::string> MENTORSHIP_COLUMNS = {"ID", "student", "mentor"};
const std::vector<std::string> SCHOOL_COLUMNS = {"ID", "name"};

// Full column names (for display/reference, though not strictly used in all operations)
const std::vector<std::string> FULL_PEOPLE_COLUMNS = {"ID", "Name", "Age", "SchoolID", "Type"};
const std::vector<std::string> FULL_MENTORSHIP_COLUMNS = {"ID", "StudentID", "FacultyID"};
const std::vector<std::string> FULL_SCHOOL_COLUMNS = {"ID", "SchoolName"};

// Commands supported by the CLI
const std::vector<std::string> COMMANDS = {"add", "search", "delete", "update", "mentor"};

// Targets (Entities) supported by the CLI
const std::vector<std::string> TARGETS = {"person", "school"};

// --- Database File Paths ---
const std::string DB_NAME = "university_management.db";
const std::string PEOPLE_SQL_NAME = "sql/people.sql";
const std::string MENTORSHIP_SQL_NAME = "sql/mentorship.sql";
const std::string SCHOOL_SQL_NAME = "sql/school.sql";

// --- Status Codes ---
const int SUCCESS = 0;
const int DB_OPEN_ERROR = 1;
const int INVALID_OPTION = 2;
const int NOT_ENOUGH_OPTIONS = 3;
const int RECORD_NOT_EXISTS = 4;
const int SQL_EXECUTION_ERROR = 5;
const int FAILURE = 6;

#endif // COMMON_H
