#include "utils.h"
#include <algorithm>
#include <vector>
#include <string>

namespace Global {
    /**
     * @brief Checks if a given string exists within a vector of strings.
     * 
     * @param values The vector of strings to search within.
     * @param value The string to search for.
     * @return true if the string is found in the vector, false otherwise.
     */
    bool contains(const std::vector<std::string>& values, const std::string& value) {
        for (const std::string& v : values) {
            if (v == value) {
                return true;
            }
        }
        return false;
    }
}
