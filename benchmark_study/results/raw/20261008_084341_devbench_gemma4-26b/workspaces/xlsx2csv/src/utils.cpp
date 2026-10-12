#include "utils.h"
#include <string>
#include <algorithm>
#include <cctype>

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
    bool found_digit = false;

    for (char c : row_column_string) {
        if (std::isdigit(static_cast<unsigned char>(c))) {
            found_digit = true;
            row_part += c;
        } else {
            col_part += c;
        }
    }

    std::uint32_t row = found_digit ? std::stoul(row_part) : 0;
    std::uint32_t col = string_to_idx(col_part);

    return {row, col};
}

std::string strip(std::string raw_string) {
    auto is_space = [](unsigned char ch) {
        return std::isspace(ch);
    };
    
    raw_string.erase(raw_string.begin(), std::find_if(raw_string.begin(), raw_string.end(), [&](int ch) {
        return !is_space(ch);
    }));
    
    raw_string.erase(std::find_if(raw_string.rbegin(), raw_string.rend(), [&](int ch) {
        return !is_space(ch);
    }).base(), raw_string.end());
    
    return raw_string;
}
