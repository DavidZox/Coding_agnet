#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <algorithm>
#include <map>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const void* workbook)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook), _cells(cells), row_num(0), column_num(0) {
    
    if (_cells.empty()) {
        row_num = 0;
        column_num = 0;
        return;
    }

    std::uint32_t max_r = 0;
    std::uint32_t max_c = 0;

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        if (r > max_r) max_r = r;
        if (col > max_c) max_c = col;
    }

    row_num = max_r;
    column_num = max_c;
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (_cells.empty()) {
        return "";
    }

    // Use a map to store cell content: map<row, map<col, content>>
    // This handles sparse data naturally.
    std::map<std::uint32_t, std::map<std::uint32_t, std::string>> grid;
    
    const workbook* wb = static_cast<const workbook*>(_workbook);

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t ss_idx = std::get<2>(c);

        std::string content = "";
        if (ss_idx > 0 && wb != nullptr) {
            content = wb->get_shared_string(ss_idx);
        } else if (ss_idx == 0) {
            // If ss_idx is 0, it might be a literal value or empty depending on implementation.
            // Based on the prompt, shared strings start from index 1.
            content = ""; 
        }

        grid[r][col] = content;
    }

    std::stringstream ss;
    for (std::uint32_t r = 1; r <= row_num; ++r) {
        bool first_in_row = true;
        for (std::uint32_t c = 1; c <= column_num; ++c) {
            if (!first_in_row) {
                ss << ",";
            }
            
            std::string cell_val = "";
            if (grid.count(r) && grid.at(r).count(c)) {
                cell_val = grid.at(r).at(c);
            }

            // Basic CSV escaping: if contains comma, quote it
            if (cell_val.find(',') != std::string::npos || cell_val.find('"') != std::string::npos || cell_val.find('\n') != std::string::npos) {
                ss << "\"";
                for (char ch : cell_val) {
                    if (ch == '"') ss << "\"\"";
                    else ss << ch;
                }
                ss << "\"";
            } else {
                ss << cell_val;
            }
            first_in_row = false;
        }
        ss << "\n";
    }

    return ss.str();
}
