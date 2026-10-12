#include "worksheet.h"
#include "workbook.h"
#include <sstream>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* workbook_ptr)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook_ptr), _cells(cells) {
    // Initialize row_num and column_num
    row_num = 0;
    column_num = 0;
    for (const auto& c : cells) {
        row_num = std::max(row_num, std::get<0>(c));
        column_num = std::max(column_num, std::get<1>(c));
    }
    // Initialize row_info
    row_info.resize(row_num);
    for (const auto& c : cells) {
        row_info[std::get<0>(c) - 1].push_back(std::get<1>(c));
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    std::ostringstream csv_data;
    for (std::uint32_t row = 0; row < row_num; ++row) {
        std::vector<std::string> row_values(column_num, "");
        for (std::uint32_t col : row_info[row]) {
            std::uint32_t ss_idx = std::get<2>(_cells[row * column_num + col - 1]);
            row_values[col - 1] = _workbook->get_shared_string(ss_idx);
        }
        for (std::uint32_t col = 0; col < column_num; ++col) {
            if (col > 0) {
                csv_data << ",";
            }
            csv_data << "\"" << row_values[col] << "\"";
        }
        csv_data << "\n";
    }
    return csv_data.str();
}
