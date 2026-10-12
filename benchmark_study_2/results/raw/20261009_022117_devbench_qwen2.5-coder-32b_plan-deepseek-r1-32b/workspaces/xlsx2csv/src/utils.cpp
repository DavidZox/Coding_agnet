#include "utils.h"
#include <cctype>
#include <algorithm>

namespace utils {
    std::uint32_t string_to_idx(const std::string& r_string) {
        std::uint32_t idx = 0;
        for (char ch : r_string) {
            idx = idx * 26 + (ch - 'A' + 1);
        }
        return idx;
    }

    std::string string_to_row_column(const std::string& row_column_string) {
        std::string row_str, col_str;
        bool is_column = true;
        for (char ch : row_column_string) {
            if (std::isalpha(ch) && is_column) {
                col_str += ch;
            } else {
                is_column = false;
                row_str += ch;
            }
        }
        std::uint32_t col_idx = string_to_idx(col_str);
        return row_str + "," + std::to_string(col_idx);
    }

    std::string strip(std::string raw_string) {
        raw_string.erase(0, raw_string.find_first_not_of(" \t\n\r\f\v"));
        raw_string.erase(raw_string.find_last_not_of(" \t\n\r\f\v") + 1);
        return raw_string;
    }
}
