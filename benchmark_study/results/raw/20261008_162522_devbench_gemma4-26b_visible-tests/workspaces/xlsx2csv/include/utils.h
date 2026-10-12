#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <cstdint>
#include <utility>

namespace my_xlsx {
namespace xlsx_reader {

std::uint32_t string_to_idx(const std::string& r_string);

std::pair<std::uint32_t, std::uint32_t> string_to_row_column(const std::string& row_column_string);

std::string strip(std::string raw_string);

} // namespace xlsx_reader
} // namespace my_xlsx

#endif // UTILS_H
