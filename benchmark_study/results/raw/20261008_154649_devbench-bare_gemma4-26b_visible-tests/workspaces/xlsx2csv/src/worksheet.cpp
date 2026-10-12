#include "worksheet.h"
#include "workbook.h"
#include "utils.h"
#include <sstream>
#include <algorithm>
#include <map>

namespace my_xlsx::xlsx_reader {

worksheet::worksheet(const std::vector<cell>& cells, 
                     std::uint32_t sheet_id, 
                     const std::string& name, 
                     const workbook* workbook_ptr)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook_ptr), _cells(cells), 
      row_num(0), column_num(0) {
    
    // row_info will store the maximum shared_string_idx for each (row, col)
    // However, based on the cell definition (row, col, ss_idx), 
    // we need to find the dimensions and organize data.
    
    if (_cells.empty()) {
        row_num = 0;
        column_num = 0;
        return;
    }

    std::uint32_t max_row = 0;
    std::uint32_t max_col = 0;

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        if (r > max_row) max_row = r;
        if (col > max_col) max_col = col;
    }

    row_num = max_row;
    column_num = max_col;

    // Initialize row_info with 0s. 
    // row_info[row-1][col-1] will store the shared string index.
    row_info.resize(row_num, std::vector<std::uint32_t>(column_num, 0));

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t ss_idx = std::get<2>(c);
        
        if (r > 0 && col > 0) {
            row_info[r - 1][col - 1] = ss_idx;
        }
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (row_num == 0 || column_num == 0) {
        return "";
    }

    std::stringstream ss;

    for (std::uint32_t r = 0; r < row_num; ++r) {
        for (std::uint32_t c = 0; c < column_num; ++c) {
            std::uint32_t ss_idx = row_info[r][c];
            
            // If ss_idx is 0, it might be an empty cell or index 0.
            // In XLSX shared strings, index 0 is a valid string.
            // However, the workbook implementation notes shared strings start from index 1.
            // We must check if the cell actually exists in the _cells vector.
            // A simple way is to check if the value in row_info is non-zero 
            // OR if we need to handle the case where the cell is actually empty.
            
            // To be precise, we should check if this (r+1, c+1) was in the original _cells.
            // But since we initialized row_info with 0, and the workbook handles 
            // shared strings starting from 1, we can treat 0 as "empty".
            
            if (ss_idx > 0) {
                ss << _workbook->get_shared_string(ss_idx);
            }

            if (c < column_num - 1) {
                ss << ",";
            }
        }
        ss << "\n";
    }

    return ss.str();
}

} // namespace my_xlsx::xlsx_reader
