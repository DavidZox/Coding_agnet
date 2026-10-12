#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <algorithm>
#include <map>

worksheet::worksheet(const std::vector<my_xlsx::xlsx_reader::cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* wb)
    : _name(name), _sheet_id(sheet_id), _workbook(wb), _cells(cells), row_num(0), column_num(0) {
    
    if (_cells.empty()) {
        row_num = 0;
        column_num = 0;
        return;
    }

    // Initialize row_info to track columns present in each row
    // We'll use a map-like structure or a vector of vectors to store column indices for each row
    // Since row_num can be large, we first find the max row index
    std::uint32_t max_row = 0;
    for (const auto& c : _cells) {
        if (std::get<0>(c) > max_row) max_row = std::get<0>(c);
    }
    
    row_num = max_row;
    row_info.resize(row_num + 1);

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        
        if (col > column_num) column_num = col;
        
        // Store the column index in the row_info for this row
        row_info[r].push_back(col);
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (row_num == 0) return "";

    // Use a map to store cell values for easy access: map<row, map<col, value>>
    std::map<std::uint32_t, std::map<std::uint32_t, std::string>> grid;

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t ss_idx = std::get<2>(c);

        std::string value;
        if (ss_idx > 0 && _workbook != nullptr) {
            value = _workbook->get_shared_string(ss_idx);
        } else if (ss_idx == 0) {
            // If ss_idx is 0, it might be a raw number or empty depending on implementation
            // But based on UML, ss_idx is the index in workbook.shared_string
            // If it's 0, we treat it as empty or handle as per requirement.
            value = "";
        }

        // Handle CSV escaping (if value contains comma, quotes, or newlines)
        if (value.find(',') != std::string::npos || value.find('"') != std::string::npos || value.find('\n') != std::string::npos) {
            std::string escaped = "\"";
            for (char ch : value) {
                if (ch == '"') escaped += "\"\"";
                else escaped += ch;
            }
            escaped += "\"";
            value = escaped;
        }

        grid[r][col] = value;
    }

    std::stringstream ss;
    for (std::uint32_t r = 1; r <= row_num; ++r) {
        for (std::uint32_t c = 1; c <= column_num; ++c) {
            if (grid.count(r) && grid.at(r).count(c)) {
                ss << grid.at(r).at(c);
            }
            
            if (c < column_num) {
                ss << ",";
            }
        }
        ss << "\n";
    }

    return ss.str();
}
