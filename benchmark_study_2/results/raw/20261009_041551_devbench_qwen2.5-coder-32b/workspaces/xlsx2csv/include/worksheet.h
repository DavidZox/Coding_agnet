#ifndef WORKSHEET_H
#define WORKSHEET_H

#include <string>
#include <vector>
#include <tuple>
#include <memory>

namespace xlsx2csv {

using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

class worksheet {
public:
    worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const void* workbook);
    std::string get_name() const;
    std::string to_csv() const;

private:
    const std::string _name;
    const std::uint32_t _sheet_id;
    const void* _workbook;
    const std::vector<cell> _cells;
    std::uint32_t row_num;
    std::uint32_t column_num;
    std::vector<std::vector<std::uint32_t>> row_info;
};

} // namespace xlsx2csv

#endif // WORKSHEET_H
