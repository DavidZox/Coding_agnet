#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

// Convert a column string (e.g., "A", "B", "AA") to a 1-based index.
std::uint32_t string_to_idx(const std::string& r_string);

// Convert a cell string (e.g., "C1", "B2") to a "row,column" string (e.g., "1,3", "2,2").
std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);

// Remove leading and trailing spaces, newlines, and tabs from a string.
std::string strip(std::string raw_string);

#endif // UTILS_H
