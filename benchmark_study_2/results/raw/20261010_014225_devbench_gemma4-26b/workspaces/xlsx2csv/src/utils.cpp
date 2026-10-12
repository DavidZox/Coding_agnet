#include "utils.h"
#include <string>
#include <algorithm>
#include <cctype>

std::uint32_t string_to_idx(const std::string& r_string) {
    std::uint32_t idx = 0;
    for (char c : r_string) {
        if (std::isupper(c)) {
            idx = idx * 26 + (c - 'A' + 1);
        } else if (std::islower(c)) {
            idx = idx * 26 + (c - 'a' + 1);
        }
    }
    return idx;
}

std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string) {
    size_t first_digit = row_column_string.find_first_of("0123456789");
    if (first_digit == std::string::npos) {
        return {0, 0};
    }

    std::string col_part = row_column_string.substr(0, first_digit);
    std::string row_part = row_column_string.substr(first_digit);

    std::uint32_t col = string_to_idx(col_part);
    std::uint32_t row = std::stoul(row_part);

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
