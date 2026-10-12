#ifndef COMMON_H
#define COMMON_H

#include <string>
#include <vector>
#include <map>
#include <algorithm> // Include for std::find

const std::vector<std::string> columns = {"ID", "name", "age", "school", "type"};
const std::vector<std::string> full_columns = {"ID", "name", "age", "school", "type", "student", "mentor"};
const std::vector<std::string> commands = {"add", "search", "delete", "update", "mentor"};
const std::vector<std::string> targets = {"person", "school"};

const std::string people_sql_name = "../sql/people.sql";
const std::string mentorship_sql_name = "../sql/mentorship.sql";
const std::string school_sql_name = "../sql/school.sql";

const std::string db_name = "university.db";

const int SUCCESS = 0;
const int DB_OPEN_ERROR = 1;
const int INVALID_OPTION = 2;
const int NOT_ENOUGH_OPTIONS = 3;
const int RECORD_NOT_EXISTS = 4;
const int SQL_EXECUTION_ERROR = 5;
const int FAILURE = 6;

class PeopleManagement; // Forward declaration

class Global {
public:
    static bool contains(const std::vector<std::string>& values, const std::string& value);
    static bool validate_options(const std::string& subcommand, const std::string& target);
    static std::map<std::string, std::string> build_options(const std::vector<std::string>& args);
    static int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, PeopleManagement& people_management);
    static const int SUCCESS;
    static const int DB_OPEN_ERROR;
    static const int INVALID_OPTION;
    static const int NOT_ENOUGH_OPTIONS;
    static const int RECORD_NOT_EXISTS;
    static const int SQL_EXECUTION_ERROR;
    static const int FAILURE;
};

bool Global::contains(const std::vector<std::string>& values, const std::string& value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}

bool Global::validate_options(const std::string& subcommand, const std::string& target) {
    if (!contains(commands, subcommand)) {
        return false;
    }
    if (!contains(targets, target)) {
        return false;
    }
    return true;
}

std::map<std::string, std::string> Global::build_options(const std::vector<std::string>& args) {
    std::map<std::string, std::string> options;
    for (size_t i = 0; i < args.size(); i += 2) {
        if (i + 1 < args.size()) {
            options[args[i]] = args[i + 1];
        }
    }
    return options;
}

int Global::handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, PeopleManagement& people_management) {
    if (subcommand == "add") {
        return people_management.add(target, options);
    } else if (subcommand == "search") {
        return people_management.search(target, options);
    } else if (subcommand == "delete") {
        return people_management.delete_record(target, options);
    } else if (subcommand == "update") {
        return people_management.update(target, options);
    } else if (subcommand == "mentor") {
        return people_management.mentor(target, options);
    }
    return INVALID_OPTION;
}

const int Global::SUCCESS = 0;
const int Global::DB_OPEN_ERROR = 1;
const int Global::INVALID_OPTION = 2;
const int Global::NOT_ENOUGH_OPTIONS = 3;
const int Global::RECORD_NOT_EXISTS = 4;
const int Global::SQL_EXECUTION_ERROR = 5;
const int Global::FAILURE = 6;

#endif // COMMON_H
