#include "worksheet.h"
#include "workbook.h"
#include <sstream>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* workbook)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook), _cells(cells), row_num(0), column_num(0) {
    // Determine the number of rows and columns
    for (const auto& c : cells) {
        std::uint32_t row = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        row_num = std::max(row_num, row);
        column_num = std::max(column_num, col);
    }

    // Initialize row_info with empty vectors for each row
    row_info.resize(row_num);

    // Populate row_info with column indices
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
    std::ostringstream csv;
    for (std::uint32_t row = 0; row < row_num; ++row) {
        for (std::uint32_t col = 0; col < column_num; ++col) {
            if (col > 0) {
                csv << ",";
            }
            bool found = false;
            for (const auto& c : _cells) {
                if (std::get<0>(c) == row + 1 && std::get<1>(c) == col + 1) {
                    std::uint32_t ss_idx = std::get<2>(c);
                    csv << _workbook->get_shared_string(ss_idx);
                    found = true;
                    break;
                }
            }
            if (!found) {
                csv << "";
            }
        }
        csv << "\n";
    }
    return csv.str();
}
