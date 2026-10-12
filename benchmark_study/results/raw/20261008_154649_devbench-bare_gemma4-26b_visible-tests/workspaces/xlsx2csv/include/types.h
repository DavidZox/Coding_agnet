#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <cstdint>

namespace my_xlsx::xlsx_reader {

/**
 * @brief sheet_desc: Stores information of sheet relation.
 * The first element is the sheet name, the second element is the sheet id, 
 * the third element is the sheet relation ID.
 * For example: std::make_tuple("Sheet1", 1, "rId1")
 */
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

/**
 * @brief cell: Stores the information of a cell.
 * The first element is the row id, the second element is the column id, 
 * the third element is the shared string id.
 * For example: std::make_tuple(1, 1, 1), std::make_tuple(3, 2, 10)
 */
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

} // namespace my_xlsx::xlsx_reader

#endif // TYPES_H
