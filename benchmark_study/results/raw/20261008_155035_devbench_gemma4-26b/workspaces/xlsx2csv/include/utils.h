#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

/**
 * @brief Converts an Excel column string (e.g., "A", "B", "AA") to a 1-based index.
 * @param r_string The column string.
 * @return The 1-based index.
 */
std::uint32_t string_to_idx(const std::string& r_string);

/**
 * @brief Converts an Excel cell reference (e.g., "A1") to a row and column pair.
 * @param row_column_string The cell reference string.
 * @return A pair containing (row, column) as 1-based indices.
 */
std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);

/**
 * @brief Removes leading and trailing whitespace (space, newline, tab) from a string.
 * @param raw_string The input string.
 * @return The stripped string.
 */
std::string strip(std::string raw_string);

#endif // UTILS_H
