#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

/**
 * @brief Convert a column string (e.g., "A", "B", "AA") to a 1-based index.
 * @param r_string The column string.
 * @return The 1-based index.
 */
std::uint32_t string_to_idx(const std::string& r_string);

/**
 * @brief Convert a cell coordinate string (e.g., "A1", "C10") to a row-column string.
 * @param row_column_string The cell coordinate string.
 * @return A string in the format "row,column".
 */
std::string string_to_row_column(const std::string& row_column_string);

/**
 * @brief Remove leading and trailing whitespace (space, newline, tab) from a string.
 * @param raw_string The string to be stripped.
 * @return The stripped string.
 */
std::string strip(std::string raw_string);

#endif // UTILS_H
