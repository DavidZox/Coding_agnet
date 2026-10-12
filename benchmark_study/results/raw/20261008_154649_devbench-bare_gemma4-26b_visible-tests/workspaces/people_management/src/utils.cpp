#include "utils.h"
#include <algorithm>

/**
 * @brief Checks if a given string exists within a vector of strings.
 * 
 * @param values The vector of strings to search through.
 * @param value The string value to look for.
 * @return true if the value is found, false otherwise.
 */
bool contains(const std::vector<std::string>& values, const std::string& value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}
