#include "../include/utils.h"
#include <algorithm>
#include <cctype>
#include <string>
#include <utility>
#include <iostream>

namespace global_functions_and_types {

/**
 * @brief Convert a string representation of a column (e.g., "A", "AA") to a 1-based index.
 * 
 * @param r_string The column string (e.g., "A").
 * @return std::uint32_t The 1-based index of the column.
 */
std::uint32_t string_to_idx(const std::string& r_string) {
    std::uint32_t index = 0;
    for (char c : r_string) {
        if (std::isupper(c)) {
            index = index * 26 + (c - 'A' + 1);
        }
    }
    return index;
}

/**
 * @brief Convert a cell reference string (e.g., "C1", "B2") to a comma-separated row and column string.
 * 
 * @param row_column_string The cell reference (e.g., "C1").
 * @return std::string A comma-separated string of row and column indices (e.g., "1,3").
 */
std::string string_to_row_column(const std::string& row_column_string) {
    std::string col_str;
    std::string row_str;
    size_t split_pos = 0;

    // Find the split point between column letters and row numbers
    for (size_t i = 0; i < row_column_string.length(); ++i) {
        if (std::isdigit(row_column_string[i])) {
            split_pos = i;
            break;
        }
    }

    if (split_pos == 0) {
        // Should not happen for valid cell references, but handle defensively
        return "0,0";
    }

    col_str = row_column_string.substr(0, split_pos);
    row_str = row_column_string.substr(split_pos);

    // Convert column string to 1-based index
    std::uint32_t col_idx = string_to_idx(col_str);

    // Convert row string to 1-based index
    std::uint32_t row_idx = 0;
    try {
        row_idx = std::stoul(row_str);
    } catch (...) {
        row_idx = 0; // Error in parsing row number
    }

    return std::to_string(row_idx) + "," + std::to_string(col_idx);
}

/**
 * @brief Remove leading and trailing whitespace characters (" ", "\n", "\t") from a string.
 * 
 * @param raw_string The string to strip.
 * @return std::string The stripped string.
 */
std::string strip(std::string raw_string) {
    // Trim leading whitespace: " ", "\n", "\t"
    raw_string.erase(raw_string.begin(), std::find_if(raw_string.begin(), raw_string.end(), [](unsigned char ch) {
        return ch != ' ' && ch != '\n' && ch != '\t';
    }));

    // Trim trailing whitespace: " ", "\n", "\t"
    raw_string.erase(std::find_if(raw_string.rbegin(), raw_string.rend(), [](unsigned char ch) {
        return ch != ' ' && ch != '\n' && ch != '\t';
    }).base(), raw_string.end());

    return raw_string;
}

} // namespace global_functions_and_types
