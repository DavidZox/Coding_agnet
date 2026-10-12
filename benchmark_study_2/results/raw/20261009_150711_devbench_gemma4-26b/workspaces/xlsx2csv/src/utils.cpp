#include "utils.h"
#include <string>
#include <algorithm>
#include <cctype>
#include <stdexcept>

namespace {
    // Helper to convert column string (e.g., "A", "AA") to index (1, 27)
    std::uint32_t column_to_idx(const std::string& col_str) {
        std::uint32_t idx = 0;
        for (char c : col_str) {
            if (std::isupper(c)) {
                idx = idx * 26 + (c - 'A' + 1);
            } else if (std::islower(c)) {
                idx = idx * 26 + (c - 'a' + 1);
            } else {
                throw std::invalid_argument("Invalid character in column string");
            }
        }
        return idx;
    }
}

std::uint32_t string_to_idx(const std::string& r_string) {
    if (r_string.empty()) return 0;
    return column_to_idx(r_string);
}

std::string string_to_row_column(const std::string& row_column_string) {
    if (row_column_string.empty()) return "0,0";

    // Find where the digits start to separate column letters from row numbers
    size_t first_digit = row_column_string.find_first_of("0123456789");
    if (first_digit == std::string::npos) {
        throw std::invalid_argument("Invalid row-column format");
    }

    std::string col_part = row_column_string.substr(0, first_digit);
    std::string row_part = row_column_string.substr(first_digit);

    std::uint32_t col = column_to_idx(col_part);
    std::uint32_t row = std::stoul(row_part);

    return std::to_string(row) + "," + std::to_string(col);
}

std::string strip(std::string raw_string) {
    // Remove leading whitespace
    raw_string.erase(raw_string.begin(), std::find_if(raw_string.begin(), raw_string.end(), [](unsigned char ch) {
        return !std::isspace(ch);
    }));

    // Remove trailing whitespace
    raw_string.erase(std::find_if(raw_string.rbegin(), raw_string.rend(), [](unsigned char ch) {
        return !std::isspace(ch);
    }).base(), raw_string.end());

    return raw_string;
}
