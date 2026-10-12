#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <utility>
#include <cctype>

namespace utils {
    std::uint32_t string_to_idx(const std::string& r_string);
    std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);
    std::string strip(std::string raw_string);
}

#endif // UTILS_H
