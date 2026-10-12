#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

namespace my_xlsx::xlsx_reader {

/**
 * @brief Converts a column string (e.g., "A", "B", "AA") to a 1-based index.
 * @param r_string The column string.
 * @return The 1-based index.
 */
std::uint32_t string_to_idx(const std::string& r_string);

/**
 * @brief Converts a cell coordinate string (e.g., "A1", "B2") to a row and column pair.
 * @param row_column_string The cell coordinate string.
 * @return A pair where first is row index and second is column index (both 1-based).
 *         Note: The specification example "C1" -> "1,3" suggests the return type 
 *         is actually a string or a pair. Based on UML and architecture, 
 *         it returns a pair of uint32_t.
 */
std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);

/**
 * @brief Removes leading and trailing whitespace (space, newline, tab) from a string.
 * @param raw_string The string to strip.
 * @return The stripped string.
 */
std::string strip(std::string raw_string);

} // namespace my_xlsx::xlsx_reader

#endif // UTILS_H
