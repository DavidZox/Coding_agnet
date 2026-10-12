#include "worksheet.h"
#include "workbook.h"
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* workbook)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook), _cells(cells) {
    row_num = 0;
    column_num = 0;

    for (const auto& c : _cells) {
        std::uint32_t row = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        if (row > row_num) {
            row_num = row;
        }
        if (col > column_num) {
            column_num = col;
        }
    }

    row_info.resize(row_num);
    for (const auto& c : _cells) {
        std::uint32_t row = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        row_info[row - 1].push_back(col);
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    std::ostringstream oss;
    for (std::uint32_t row = 0; row < row_num; ++row) {
        for (std::uint32_t col = 0; col < column_num; ++col) {
            bool found = false;
            for (const auto& cell_col : row_info[row]) {
                if (cell_col == col + 1) {
                    for (const auto& c : _cells) {
                        if (std::get<0>(c) == row + 1 && std::get<1>(c) == col + 1) {
                            std::uint32_t shared_string_idx = std::get<2>(c);
                            std::string value = _workbook->get_shared_string(shared_string_idx);
                            if (!value.empty()) {
                                oss << "\"" << value << "\"";
                            }
                            found = true;
                            break;
                        }
                    }
                }
            }
            if (!found && col < column_num - 1) {
                oss << ",";
            }
        }
        if (row < row_num - 1) {
            oss << "\n";
        }
    }
    return oss.str();
}
