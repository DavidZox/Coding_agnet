#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <cstdint>

// sheet_desc: Tuple(sheet_name, sheet_id, sheet_relation_id)
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

// cell: Tuple(row_id, column_id, shared_string_id)
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

#endif // TYPES_H
