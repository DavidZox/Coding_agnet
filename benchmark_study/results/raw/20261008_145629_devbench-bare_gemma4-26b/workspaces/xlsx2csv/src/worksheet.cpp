#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <algorithm>
#include <map>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* wb)
    : _name(name), _sheet_id(sheet_id), _workbook(wb), _cells(cells), row_num(0), column_num(0) {
    
    if (_cells.empty()) {
        return;
    }

    // Find max row and column to determine dimensions
    std::uint32_t max_r = 0;
    std::uint32_t max_c = 0;
    
    // row_info will store the max column index for each row to handle sparse data
    // We use a map-like structure via row_info to track the grid
    // Since row_info is vector<vector<uint32_t>>, we'll use it to store column indices present in each row
    // However, to build a proper CSV, we need to know the bounds.
    
    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t val = std::get<2>(c);

        if (r > max_r) max_r = r;
        if (col > max_c) max_c = col;
    }

    row_num = max_r;
    column_num = max_c;

    // Initialize row_info with size (max_r + 1)
    // We'll use a 2D structure to represent the grid: grid[row][col] = shared_string_id
    // But the header defines row_info as vector<vector<uint32_t>>. 
    // To satisfy the UML/Architecture, we'll use it to store the cell values.
    // Since CSV needs a dense grid, we'll use a temporary map to build the rows.
    
    std::map<std::uint32_t, std::map<std::uint32_t, std::uint32_t>> grid;
    for (const auto& c : _cells) {
        grid[std::get<0>(c)][std::get<1>(c)] = std::get<2>(c);
    }

    row_info.resize(row_num + 1);
    for (auto const& [r, cols] : grid) {
        // We need to ensure row_info[r] is large enough to hold the columns.
        // However, the type is vector<vector<uint32_t>>, which is usually used for adjacency lists.
        // Given the context of CSV, we will treat row_info[r][c] as the value at (r, c).
        // To make this work with vector<vector<uint32_t>>, we must resize each inner vector.
        row_info[r].resize(column_num + 1, 0); 
        for (auto const& [c, val] : cols) {
            row_info[r][c] = val;
        }
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (row_num == 0 && column_num == 0) {
        return "";
    }

    std::stringstream ss;

    for (std::uint32_t r = 1; r <= row_num; ++r) {
        // Check if this row exists in our row_info
        if (r >= row_info.size()) continue;

        for (std::uint32_t c = 1; c <= column_num; ++c) {
            // Check if column exists in this row
            if (c < row_info[r].size()) {
                std::uint32_t ss_idx = row_info[r][c];
                if (ss_idx > 0 && _workbook) {
                    ss << _workbook->get_shared_string(ss_idx);
                }
            }

            if (c < column_num) {
                ss << ",";
            }
        }
        ss << "\n";
    }

    return ss.str();
}
