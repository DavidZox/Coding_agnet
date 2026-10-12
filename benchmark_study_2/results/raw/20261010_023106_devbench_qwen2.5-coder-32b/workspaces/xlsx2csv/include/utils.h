#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <utility>
#include <algorithm>

namespace utils {
    std::uint32_t string_to_idx(const std::string& r_string) {
        std::uint32_t idx = 0;
        for (char c : r_string) {
            idx = idx * 26 + (c - 'A' + 1);
        }
        return idx;
    }

    std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string) {
        std::uint32_t row = 0;
        std::uint32_t column = 0;
        std::size_t i = 0;
        while (i < row_column_string.size() && std::isalpha(row_column_string[i])) {
            column = column * 26 + (row_column_string[i] - 'A' + 1);
            ++i;
        }
        while (i < row_column_string.size() && std::isdigit(row_column_string[i])) {
            row = row * 10 + (row_column_string[i] - '0');
            ++i;
        }
        return {row, column};
    }

    std::string strip(std::string raw_string) {
        raw_string.erase(0, raw_string.find_first_not_of(" \n\t"));
        raw_string.erase(raw_string.find_last_not_of(" \n\t") + 1);
        return raw_string;
    }
}

#endif // UTILS_H
