#include "utils.h"
#include <algorithm>
#include <cctype>
#include <regex>

namespace my_xlsx::xlsx_reader {

std::uint32_t string_to_idx(const std::string& r_string) {
    std::uint32_t idx = 0;
    for (char c : r_string) {
        if (std::isupper(static_cast<unsigned char>(c))) {
            idx = idx * 26 + (c - 'A' + 1);
        } else {
            // Handle lowercase if necessary, though XLSX spec usually uses uppercase
            idx = idx * 26 + (std::tolower(static_cast<unsigned char>(c)) - 'a' + 1);
        }
    }
    return idx;
}

std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string) {
    // The specification example: "C1" -> "1,3" (row, col) or "A4" -> "4,1"
    // Based on the example "C1" -> "1,3", it means (row, col) where row is 1 and col is 3.
    // Wait, the example "C1" -> "1,3" implies row=1, col=3. 
    // "B2" -> "2,2" implies row=2, col=2.
    // "A4" -> "4,1" implies row=4, col=1.
    // So the pattern is (row_number, column_index).
    
    std::regex re("([A-Z]+)([0-9]+)", std::regex_constants::icase);
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

} // namespace my_xlsx::xlsx_reader
