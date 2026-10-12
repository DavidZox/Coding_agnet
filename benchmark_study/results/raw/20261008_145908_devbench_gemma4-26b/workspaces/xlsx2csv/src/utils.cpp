#include "utils.h"
#include <string>
#include <algorithm>
#include <cctype>
#include <stdexcept>

std::uint32_t string_to_idx(const std::string& r_string) {
    std::uint32_t idx = 0;
    for (char c : r_string) {
        if (std::isalpha(static_cast<unsigned char>(c))) {
            idx = idx * 26 + (std::toupper(static_cast<unsigned char>(c)) - 'A' + 1);
        } else {
            // If non-alpha characters are present, we treat them as invalid or ignore
            // but based on Excel logic, we expect only letters for column index.
        }
    }
    return idx;
}

std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string) {
    if (row_column_string.empty()) {
        return {0, 0};
    }

    std::string col_part;
    std::string row_part;
    bool found_digit = false;

    for (char c : row_column_string) {
        if (std::isdigit(static_cast<unsigned char>(c))) {
            found_digit = true;
            row_part += c;
        } else {
            col_part += c;
        }
    }

    if (!found_digit) {
        throw std::invalid_argument("Invalid row-column format");
    }

    std::uint32_t col = string_to_idx(col_part);
    std::uint32_t row = std::stoul(row_part);

    // The requirement says "C1" -> "1,3" (row, column)
    // Note: The architecture design says return std::string "1,3", 
    // but the UML says return std::pair<std::uint32_t, std::uint32_t>.
    // I will follow the UML signature as it is more programmatic.
    // However, the prompt description says "convert a string to a row-column string".
    // Looking at the UML: string_to_row_column(const std::string&) : std::pair<std::uint32_t, std::uint32_t>
    // I will implement the UML signature.
    
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
