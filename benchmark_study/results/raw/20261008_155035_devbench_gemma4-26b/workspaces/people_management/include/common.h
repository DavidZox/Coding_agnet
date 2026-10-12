#pragma once

// Status codes
const int SUCCESS = 0;
const int DB_OPEN_ERROR = 1;
const int INVALID_OPTION = 2;
const int NOT_ENOUGH_OPTIONS = 3;
const int RECORD_NOT_EXISTS = 4;
const int SQL_EXECUTION_ERROR = 5;
const int FAILURE = 6;

// Database configuration
const char* const db_name = "umm.db";
const char* const people_sql_name = "sql/people.sql";
const char* const mentorship_sql_name = "sql/mentorship.sql";
const char* const school_sql_name = "sql/school.sql";

// Commands and targets
const char* const commands[] = {"add", "search", "delete", "mentor", "update"};
const char* const targets[] = {"person", "school"};

// Column names
const char* const columns[] = {"-name", "-age", "-school", "-type", "-id", "-student", "-mentor"};
const char* const full_columns[] = {"name", "age", "school", "type", "id", "student", "mentor"};
