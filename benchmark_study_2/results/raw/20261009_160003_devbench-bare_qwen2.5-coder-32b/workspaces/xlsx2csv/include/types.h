#ifndef TYPES_H
#define TYPES_H

#include <string>
#include <tuple>
#include <vector>
#include <cstdint>
#include <unordered_map>
#include <memory>

namespace xlsx2csv {

using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

} // namespace xlsx2csv

#endif // TYPES_H
