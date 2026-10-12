#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <cstdint>

// sheet_desc: std::tuple<sheet name, sheet id, sheet relation ID>
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

// cell: std::tuple<row id, column id, shared string id>
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

#endif // TYPES_H
