#include "utils.h"
#include <vector>
#include <string>

bool contains(const std::vector<std::string>& values, const std::string& value) {
    for (const std::string& val : values) {
        if (val == value) {
            return true;
        }
    }
    return false;
}
