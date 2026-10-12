#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <algorithm>
#include <map>
#include <vector>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const void* workbook)
    : _cells(cells), _sheet_id(sheet_id), _name(name), _workbook(workbook) {
    
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

    // row_info stores the column indices for each row to handle sparse data
    // However, for a standard CSV, we need to ensure every row has the same number of columns.
    // We will use a map-like structure or a 2D vector to represent the grid.
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (_cells.empty()) {
        return "";
    }

    // Find dimensions
    std::uint32_t max_r = 0;
    std::uint32_t max_c = 0;
    for (const auto& c : _cells) {
        max_r = std::max(max_r, std::get<0>(c));
        max_c = std::max(max_c, std::get<1>(c));
    }

    // Use a map to store cell values: map<row, map<col, string>>
    std::map<std::uint32_t, std::map<std::uint32_t, std::string>> grid;

    const workbook* wb = static_cast<const workbook*>(_workbook);

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t s_idx = std::get<2>(c);

        std::string val;
        if (s_idx > 0 && wb != nullptr) {
            val = wb->get_shared_string(s_idx);
        } else if (s_idx == 0) {
            // If s_idx is 0, it might be a literal value or empty. 
            // Based on UML, s_idx is the index in shared_string.
            // If the cell is not a shared string, it's usually handled differently, 
            // but here we follow the provided logic.
            val = ""; 
        }

        // Escape CSV special characters: " -> ""
        size_t pos = 0;
        while ((pos = val.find('"', pos)) != std::string::npos) {
            val.replace(pos, 1, "\"\"");
            pos += 2;
        }
        // Wrap in quotes
        val = "\"" + val + "\"";
        
        grid[r][col] = val;
    }

    std::stringstream ss;
    for (std::uint32_t r = 1; r <= max_r; ++r) {
        for (std::uint32_t c = 1; c <= max_c; ++c) {
            if (grid.count(r) && grid.at(r).count(c)) {
                ss << grid.at(r).at(c);
            } else {
                ss << "\"\"";
            }
            if (c < max_c) {
                ss << ",";
            }
        }
        ss << "\n";
    }

    return ss.str();
}
