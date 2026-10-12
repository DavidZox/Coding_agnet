#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

namespace global_functions_and_types {

/**
 * @brief Convert a string representation of a column (e.g., "A", "AA") to a 1-based index.
 * 
 * @param r_string The column string (e.g., "A").
 * @return std::uint32_t The 1-based index of the column.
 */
std::uint32_t string_to_idx(const std::string& r_string);

/**
 * @brief Convert a cell reference string (e.g., "C1", "B2") to a comma-separated row and column string.
 * 
 * @param row_column_string The cell reference (e.g., "C1").
 * @return std::string A comma-separated string of row and column indices (e.g., "1,3").
 */
std::string string_to_row_column(const std::string& row_column_string);

/**
 * @brief Remove leading and trailing whitespace characters (" ", "\n", "\t") from a string.
 * 
 * @param raw_string The string to strip.
 * @return std::string The stripped string.
 */
std::string strip(std::string raw_string);

} // namespace global_functions_and_types

#endif // UTILS_H
