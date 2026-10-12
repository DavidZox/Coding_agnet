#ifndef WORKSHEET_H
#define WORKSHEET_H

#include <string>
#include <vector>
#include <tuple>
#include <unordered_map>
#include "types.h"

class workbook;

class worksheet {
public:
    worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* workbook);
    std::string get_name() const;
    std::string to_csv() const;

private:
    const std::string _name;
    const std::uint32_t _sheet_id;
    const workbook* _workbook;
    const std::vector<cell> _cells;
    std::uint32_t row_num;
    std::uint32_t column_num;
    std::vector<std::vector<std::uint32_t>> row_info;
};

#endif // WORKSHEET_H
