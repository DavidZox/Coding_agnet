#include "utils.h"
#include <string>
#include <cctype>
#include <algorithm>

namespace utils {
    std::uint32_t string_to_idx(const std::string& r_string) {
        std::uint32_t idx = 0;
        for (char ch : r_string) {
            if (std::isalpha(ch)) {
                idx = idx * 26 + (std::toupper(ch) - 'A' + 1);
            }
        }
        return idx;
    }

    std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string) {
        std::string row_str, col_str;
        for (char ch : row_column_string) {
            if (std::isalpha(ch)) {
                col_str += ch;
            } else if (std::isdigit(ch)) {
                row_str += ch;
            }
        }
        std::uint32_t col_idx = string_to_idx(col_str);
        std::uint32_t row_idx = std::stoi(row_str);
        return {row_idx, col_idx};
    }

    std::string strip(std::string raw_string) {
        raw_string.erase(raw_string.begin(), std::find_if(raw_string.begin(), raw_string.end(), [](unsigned char ch) {
            return !std::isspace(ch);
        }));
        raw_string.erase(std::find_if(raw_string.rbegin(), raw_string.rend(), [](unsigned char ch) {
            return !std::isspace(ch);
        }).base(), raw_string.end());
        return raw_string;
    }
}
