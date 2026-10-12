#include "utils.h"
#include <string>
#include <algorithm>
#include <cctype>

namespace my_xlsx {
namespace xlsx_reader {

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
    
    for (char c : row_column_string) {
        if (std::isalpha(static_cast<unsigned char>(c))) {
            col_part += c;
        } else if (std::isdigit(static_cast<unsigned char>(c))) {
            row_part += c;
        }
    }

    std::uint32_t row = row_part.empty() ? 0 : std::stoul(row_part);
    std::uint32_t col = string_to_idx(col_part);
    
    return {row, col};
}

std::string strip(std::string raw_string) {
    auto is_space = [](unsigned char ch) {
        return std::isspace(ch) || ch == ' ' || ch == '\n' || ch == '\r' || ch == '\t';
    };

    raw_string.erase(raw_string.begin(), std::find_if(raw_string.begin(), raw_string.end(), [&](int ch) {
        return !is_space(static_cast<unsigned char>(ch));
    }));
    
    raw_string.erase(std::find_if(raw_string.rbegin(), raw_string.rend(), [&](int ch) {
        return !is_space(static_cast<unsigned char>(ch));
    }).base(), raw_string.end());

    return raw_string;
}

} // namespace xlsx_reader
} // namespace my_xlsx
