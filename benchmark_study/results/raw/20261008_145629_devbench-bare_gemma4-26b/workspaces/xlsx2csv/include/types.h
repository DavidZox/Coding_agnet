#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <cstdint>

/**
 * @brief sheet_desc: Stores information of sheet relation.
 * Tuple elements: (sheet name, sheet id, sheet relation ID)
 * Example: std::make_tuple("Sheet1", 1, "rId1")
 */
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

/**
 * @brief cell: Stores information of a cell.
 * Tuple elements: (row id, column id, shared string id)
 * The shared string id is the index in workbook.shared_string.
 * Example: std::make_tuple(1, 1, 1)
 */
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

#endif // TYPES_H
