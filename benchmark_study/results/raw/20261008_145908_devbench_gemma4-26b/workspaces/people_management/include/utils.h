#ifndef UTILS_H
#define UTILS_H

#include <iostream>
#include <vector>
#include <string>

/**
 * @brief Checks if a string is in a vector of strings.
 * 
 * @param values The vector of strings to search in.
 * @param value The string to look for.
 * @return true if the value is found, false otherwise.
 */
bool contains(const std::vector<std::string>& values, const std::string& value);

#endif // UTILS_H
