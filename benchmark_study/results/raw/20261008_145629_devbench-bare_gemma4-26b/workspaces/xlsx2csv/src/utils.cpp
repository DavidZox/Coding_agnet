#include "utils.h"
#include <algorithm>
#include <cctype>
#include <regex>

std::uint32_t string_to_idx(const std::string& r_string) {
    std::uint32_t idx = 0;
    for (char c : r_string) {
        if (std::isupper(static_cast<unsigned char>(c))) {
            idx = idx * 26 + (c - 'A' + 1);
        } else if (std::islower(static_cast<unsigned char>(c))) {
            idx = idx * 26 + (c - 'a' + 1);
        }
    }
    return idx;
}

std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string) {
    std::regex re("([A-Za-z]+)([0-9]+)");
    std::smatch match;
    if (std::regex_search(row_column_string, match, re)) {
        std::string col_part = match[1].str();
        std::string row_part = match[2].str();
        
        std::uint32_t col = string_to_idx(col_part);
        std::uint32_t row = std::stoul(row_part);
        
        return {row, col};
    }
    return {0, 0};
}

std::string strip(std::string raw_string) {
    auto is_whitespace = [](unsigned char ch) {
        return ch == ' ' || ch == '\n' || ch == '\t' || ch == '\r';
    };
    
    raw_string.erase(raw_string.begin(), std::find_if(raw_string.begin(), raw_string.end(), [is_whitespace](unsigned char ch) {
        return !is_whitespace(ch);
    }));
    
    raw_string.erase(std::find_if(raw_string.rbegin(), raw_string.rend(), [is_whitespace](unsigned char ch) {
        return !is_whitespace(ch);
    }).base(), raw_string.end());
    
    return raw_string;
}
