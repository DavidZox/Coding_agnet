#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

namespace my_xlsx {
namespace xlsx_reader {

// Convert a column string (e.g., "A", "B", "AA") to a 1-based index.
std::uint32_t string_to_idx(const std::string& r_string);

// Convert a cell reference (e.g., "C1") to a pair of (row, column).
std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);

// Remove leading and trailing spaces, newlines, and tabs.
std::string strip(std::string raw_string);

} // namespace xlsx_reader
} // namespace my_xlsx

#endif // UTILS_H
