#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <vector>
#include <cstdint>

using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

#endif // TYPES_H
