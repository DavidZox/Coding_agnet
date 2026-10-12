#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <cstdint>
#include <memory>

// Forward declarations
class archive;
class workbook;
class worksheet;

// struct sheet_desc: Tuple<sheet_name, sheet_id, sheet_relation_id>
// sheet_desc: std::tuple<std::string, std::uint32_t, std::string>
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

// struct cell: Tuple<row_id, column_id, shared_string_id>
// cell: std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

#endif // TYPES_H
