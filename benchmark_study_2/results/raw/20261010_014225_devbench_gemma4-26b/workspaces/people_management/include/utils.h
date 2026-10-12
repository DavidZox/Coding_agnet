#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <vector>
#include <map>

class Global {
public:
    static bool contains(const std::vector<std::string> values, const std::string value);
    static bool validate_options(const std::string& subcommand, const std::string& target);
    static std::map<std::string, std::string> build_options(const std::vector<std::string>& args);
    static int handle_options(const std::string& subcommand, const std::string& target, const std::map<std::string, std::string>& options, const class PeopleManagement& people_management);

    static const int SUCCESS = 0;
    static const int DB_OPEN_ERROR = 1;
    static const int INVALID_OPTION = 2;
    static const int NOT_ENOUGH_OPTIONS = 3;
    static const int RECORD_NOT_EXISTS = 4;
    static const int SQL_EXECUTION_ERROR = 5;
    static const int FAILURE = 6;
};

#endif // UTILS_H
