#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <cstdint>

// sheet_desc : std::tuple<std::string, std::uint32_t, std::string>
// The first element is the sheet name, the second element is the sheet id, the third element is the sheet relation ID.
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

// cell : std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>
// The first element is the row id, the second element is the column id, the third element is the shared string id.
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

#endif // TYPES_H
