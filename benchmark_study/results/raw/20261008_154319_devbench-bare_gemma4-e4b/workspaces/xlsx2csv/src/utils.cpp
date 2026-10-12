#include "../include/utils.h"
#include <string>
#include <algorithm>
#include <cctype>
#include <sstream>
#include <utility>

// Implementation of string_to_idx
std::uint32_t string_to_idx(const std::string& r_string) {
    std::uint32_t index = 0;
    for (char c : r_string) {
        if (c >= 'A' && c <= 'Z') {
            index = index * 26 + (c - 'A' + 1);
        }
    }
    return index;
}

// Implementation of string_to_row_column
std::string string_to_row_column(const std::string& row_column_string) {
    std::string row_str;
    std::string col_str;
    size_t pos = row_column_string.find_first_of("0123456789");

    if (pos == std::string::npos) {
        return ""; // Invalid format
    }

    // Column part (letters before the first digit)
    col_str = row_column_string.substr(0, pos);
    // Row part (digits from the first digit onwards)
    row_str = row_column_string.substr(pos);

    // Convert column string to index
    std::uint32_t col_idx = string_to_idx(col_str);

    // Convert row string to index (assuming it's a valid number)
    std::uint32_t row_idx = 0;
    try {
        row_idx = std::stoul(row_str);
    } catch (...) {
        return ""; // Invalid row number
    }

    return std::to_string(row_idx) + "," + std::to_string(col_idx);
}

// Implementation of strip
std::string strip(std::string raw_string) {
    // Trim leading whitespace
    raw_string.erase(raw_string.begin(), std::find_if(raw_string.begin(), raw_string.end(), [](unsigned char ch) {
        return !std::isspace(ch);
    }));

    // Trim trailing whitespace
    raw_string.erase(std::find_if(raw_string.rbegin(), raw_string.rend(), [](unsigned char ch) {
        return !std::isspace(ch);
    }).base(), raw_string.end());

    return raw_string;
}
