#include "utils.h"
#include <algorithm>

namespace Global {
    bool contains(const std::vector<std::string>& values, const std::string& value) {
        return std::find(values.begin(), values.end(), value) != values.end();
    }
}
