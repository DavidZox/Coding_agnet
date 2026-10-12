#include "utils.h"
#include <string>
#include <algorithm>
#include <cctype>
#include <regex>

std::uint32_t string_to_idx(const std::string& r_string) {
    std::uint32_t idx = 0;
    for (char c : r_string) {
        if (std::isalpha(static_cast<unsigned char>(c))) {
            idx = idx * 26 + (std::toupper(static_cast<unsigned char>(c)) - 'A' + 1);
        }
    }
    return idx;
}

std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string) {
    std::string col_part;
    std::string row_part;
    
    size_t first_digit = row_column_string.find_first_of("0123456789");
    
    if (first_digit == std::string::npos) {
        return {0, 0};
    }

    col_part = row_column_string.substr(0, first_digit);
    row_part = row_column_string.substr(first_digit);

    std::uint32_t col = string_to_idx(col_part);
    std::uint32_t row = 0;
    try {
        row = std::stoul(row_part);
    } catch (...) {
        row = 0;
    }

    return {row, col};
}

std::string strip(std::string raw_string) {
    auto start = raw_string.find_first_not_of(" \n\r\t");
    if (start == std::string::npos) {
        return "";
    }
    auto end = raw_string.find_last_not_of(" \n\r\t");
    return raw_string.substr(start, end - start + 1);
}
