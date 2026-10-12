#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

/**
 * @brief Convert an Excel column string (e.g., "A", "B", "AA") to a 1-based index.
 * @param r_string The column string.
 * @return The 1-based index.
 */
std::uint32_t string_to_idx(const std::string& r_string);

/**
 * @brief Convert an Excel cell reference (e.g., "C1", "B2") to a row and column pair.
 * @param row_column_string The cell reference string.
 * @return A pair where first is row index and second is column index (both 1-based).
 */
std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);

/**
 * @brief Remove leading and trailing whitespace characters (space, \n, \t) from a string.
 * @param raw_string The input string.
 * @return The stripped string.
 */
std::string strip(std::string raw_string);

#endif // UTILS_H
