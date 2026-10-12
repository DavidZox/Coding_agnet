#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <cstdint>
#include <tuple>
#include <vector>

namespace my_xlsx {
namespace xlsx_reader {

// sheet_desc: Tuple(sheet_name, sheet_id, sheet_relation_id)
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

// cell: Tuple(row_id, column_id, shared_string_id)
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

} // namespace xlsx_reader
} // namespace my_xlsx

#endif // TYPES_H
