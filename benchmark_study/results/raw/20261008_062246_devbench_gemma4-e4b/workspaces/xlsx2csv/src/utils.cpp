#include "utils.h"
#include <algorithm>
#include <cctype>
#include <sstream>

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
    // Find the split point between letters (column) and digits (row)
    size_t split_pos = 0;
    while (split_pos < row_column_string.length() && std::isalpha(row_column_string[split_pos])) {
        split_pos++;
    }

    if (split_pos == 0 || split_pos == row_column_string.length()) {
        // Invalid format, return empty or handle error as appropriate.
        // For simplicity based on examples, we assume valid input.
        return "";
    }

    std::string col_str = row_column_string.substr(0, split_pos);
    std::string row_str = row_column_string.substr(split_pos);

    // Convert column string to index
    std::uint32_t col_idx = string_to_idx(col_str);

    // Convert row string to index (assuming it's a valid number)
    std::uint32_t row_idx = 0;
    try {
        row_idx = std::stoul(row_str);
    } catch (...) {
        return ""; // Conversion failed
    }

    std::stringstream ss;
    // Format required: "row,column" based on the sequence diagram/UML context, 
    // although the description example "C1" -> "1,3" implies row, column.
    // The original implementation used row_idx, col_idx. We stick to that structure.
    ss << row_idx << "," << col_idx;
    return ss.str();
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
