#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <algorithm>
#include <map>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const void* workbook)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook), _cells(cells), row_num(0), column_num(0) {
    
    if (!_cells.empty()) {
        for (const auto& c : _cells) {
            std::uint32_t r = std::get<0>(c);
            std::uint32_t col = std::get<1>(c);
            if (r > row_num) row_num = r;
            if (col > column_num) column_num = col;
        }
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (_cells.empty()) {
        return "";
    }

    // Use a map to store cell values: map<row, map<col, value>>
    std::map<std::uint32_t, std::map<std::uint32_t, std::string>> grid;
    const workbook* wb = static_cast<const workbook*>(_workbook);

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t ss_idx = std::get<2>(c);

        std::string value;
        if (ss_idx > 0) {
            value = wb->get_shared_string(ss_idx);
        } else {
            // If ss_idx is 0, it might be a raw value (though the spec implies shared strings)
            // For this implementation, we assume ss_idx 0 means empty or handled elsewhere.
            value = "";
        }
        grid[r][col] = value;
    }

    std::stringstream ss;
    for (std::uint32_t r = 1; r <= row_num; ++r) {
        for (std::uint32_t c = 1; c <= column_num; ++c) {
            std::string cell_val = "";
            if (grid.count(r) && grid.at(r).count(c)) {
                cell_val = grid.at(r).at(c);
            }

            // Basic CSV escaping: if contains comma, quote, or newline, wrap in quotes
            bool needs_quotes = false;
            if (cell_val.find(',') != std::string::npos || 
                cell_val.find('\"') != std::string::npos || 
                cell_val.find('\n') != std::string::npos || 
                cell_val.find('\r') != std::string::npos) {
                needs_quotes = true;
            }

            if (needs_quotes) {
                ss << '\"';
                for (char ch : cell_val) {
                    if (ch == '\"') ss << "\"\""; // Escape double quotes
                    else ss << ch;
                }
                ss << '\"';
            } else {
                ss << cell_val;
            }

            if (c < column_num) {
                ss << ",";
            }
        }
        ss << "\n";
    }

    return ss.str();
}
