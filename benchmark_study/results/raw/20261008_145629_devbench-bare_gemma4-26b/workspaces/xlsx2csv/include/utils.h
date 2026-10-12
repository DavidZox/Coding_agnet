#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

/**
 * @brief Converts a column string (e.g., "A", "B", "AA") to a 1-based index.
 * @param r_string The column string.
 * @return The 1-based index of the column.
 */
std::uint32_t string_to_idx(const std::string& r_string);

/**
 * @brief Converts a cell coordinate string (e.g., "C1") to a "row,column" string.
 * @param row_column_string The cell coordinate string.
 * @return A string in the format "row,column" (e.g., "1,3").
 */
std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);

/**
 * @brief Removes leading and trailing whitespace characters (" ", "\n", "\t") from a string.
 * @param raw_string The original string.
 * @return The stripped string.
 */
std::string strip(std::string raw_string);

#endif // UTILS_H
