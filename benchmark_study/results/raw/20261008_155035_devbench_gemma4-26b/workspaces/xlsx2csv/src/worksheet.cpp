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

    // Determine max row and column to build the grid
    std::map<std::uint32_t, std::map<std::uint32_t, std::uint32_t>> grid_map;
    std::uint32_t max_r = 0;
    std::uint32_t max_c = 0;

    for (const auto& c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t val_idx = std::get<2>(c);

        grid_map[r][col] = val_idx;
        if (r > max_r) max_r = r;
        if (col > max_c) max_c = col;
    }

    row_num = max_r;
    column_num = max_c;

    // row_info stores the shared string index for each cell in a sparse-like way
    // However, to facilitate CSV generation, we'll use the grid_map logic inside to_csv
    // or pre-calculate a dense structure if needed. 
    // Given the UML, row_info is vector<vector<uint32_t>>.
    row_info.resize(row_num + 1);
    for (std::uint32_t r = 1; r <= row_num; ++r) {
        row_info[r].resize(column_num + 1, 0); // 0 indicates empty cell
        for (auto const& [col, val_idx] : grid_map[r]) {
            row_info[r][col] = val_idx;
        }
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    std::stringstream ss;
    const workbook* wb = static_cast<const workbook*>(_workbook);

    for (std::uint32_t r = 1; r <= row_num; ++r) {
        for (std::uint32_t c = 1; c <= column_num; ++c) {
            std::uint32_t val_idx = row_info[r][c];
            
            if (val_idx == 0) {
                ss << "";
            } else {
                ss << wb->get_shared_string(val_idx);
            }

            if (c < column_num) {
                ss << ",";
            }
        }
        if (r < row_num) {
            ss << "\n";
        }
    }

    return ss.str();
}
