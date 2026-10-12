#ifndef UTILS_H
#define UTILS_H

#include <vector>
#include <string>

/**
 * @brief Checks if a given string value exists within a vector of strings.
 * 
 * @param values The vector of strings to search within.
 * @param value The string value to search for.
 * @return true if the value is found in the vector, false otherwise.
 */
bool contains(const std::vector<std::string>& values, const std::string& value);

#endif // UTILS_H
