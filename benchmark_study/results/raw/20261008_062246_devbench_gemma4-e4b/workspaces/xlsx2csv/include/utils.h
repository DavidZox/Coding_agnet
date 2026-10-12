#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

// Global utility functions (as per global_functions_and_types in UML)

/**
 * @brief Converts a string representation of a column (e.g., "A", "AA") to its 1-based index.
 * @param r_string The column string (e.g., "A").
 * @return The 1-based index of the column.
 */
std::uint32_t string_to_idx(const std::string& r_string);

/**
 * @brief Converts a cell reference string (e.g., "C1", "B2") to a comma-separated row and column index string.
 * @param row_column_string The cell reference (e.g., "C1").
 * @return A string in the format "row,column" (e.g., "1,3").
 */
std::string string_to_row_column(const std::string& row_column_string);

/**
 * @brief Removes leading and trailing whitespace characters (" ", "\n", "\t") from a string.
 * @param raw_string The string to strip.
 * @return The stripped string.
 */
std::string strip(std::string raw_string);

#endif // UTILS_H
