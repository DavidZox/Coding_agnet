#include "utils.h"

bool contains(const std::vector<std::string>& values, const std::string& value) {
    for (const auto& v : values) {
        if (v == value) {
            return true;
        }
    }
    return false;
}
