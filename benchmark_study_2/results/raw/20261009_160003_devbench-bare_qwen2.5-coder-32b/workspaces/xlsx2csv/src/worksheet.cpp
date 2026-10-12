#include "worksheet.h"
#include <sstream>
#include <iomanip>

namespace xlsx2csv {

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* workbook_ptr)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook_ptr), _cells(cells) {
    row_num = 0;
    column_num = 0;

    for (const auto& c : cells) {
        std::uint32_t row = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        if (row > row_num) row_num = row;
        if (col > column_num) column_num = col;
    }

    row_info.resize(row_num);
    for (const auto& c : cells) {
        std::uint32_t row = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        row_info[row - 1].push_back(col);
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    std::ostringstream csv_stream;
    for (std::uint32_t row = 0; row < row_num; ++row) {
        for (std::uint32_t col = 0; col < column_num; ++col) {
            if (col > 0) csv_stream << ",";
            bool found = false;
            for (const auto& cell_col : row_info[row]) {
                if (cell_col == col + 1) {
                    for (const auto& c : _cells) {
                        if (std::get<0>(c) == row + 1 && std::get<1>(c) == col + 1) {
                            std::uint32_t shared_string_idx = std::get<2>(c);
                            csv_stream << "\"" << _workbook->get_shared_string(shared_string_idx) << "\"";
                            found = true;
                            break;
                        }
                    }
                }
            }
            if (!found) {
                csv_stream << "\"\"";
            }
        }
        csv_stream << "\n";
    }
    return csv_stream.str();
}

} // namespace xlsx2csv
