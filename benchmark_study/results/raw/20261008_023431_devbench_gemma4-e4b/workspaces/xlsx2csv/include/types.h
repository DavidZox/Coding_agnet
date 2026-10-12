#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <cstdint>

// sheet_desc: (Sheet Name, Sheet ID, Sheet Relation ID)
using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

// cell: (Row ID, Column ID, Shared String ID)
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

#endif // TYPES_H
