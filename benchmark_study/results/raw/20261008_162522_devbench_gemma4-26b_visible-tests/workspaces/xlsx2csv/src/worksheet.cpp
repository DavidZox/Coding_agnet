#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <algorithm>
#include <map>

namespace my_xlsx {
namespace xlsx_reader {

worksheet::worksheet(const std::vector<cell> &cells, std::uint32_t sheet_id, const std::string &name, const workbook *workbook)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook), _cells(cells), row_num(0), column_num(0), row_info() {
    
    if (_cells.empty()) {
        return;
    }

    // Use a map to store cell values for easy access during CSV generation
    // Key: {row, col}, Value: shared_string_index
    // We also need to track the max row and max column to define the grid size
    std::map<std::pair<std::uint32_t, std::uint32_t>, std::uint32_t> cell_map;
    std::uint32_t max_r = 0;
    std::uint32_t max_c = 0;

    for (const auto &c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t s_idx = std::get<2>(c);

        cell_map[{r, col}] = s_idx;
        if (r > max_r) max_r = r;
        if (col > max_c) max_c = col;

        // Update row_info: row_info[row_index] = {col_index1, col_index2, ...}
        // Assuming row/col are 1-indexed based on architecture_design.md examples
        if (row_info.size() <= r) {
            row_info.resize(r + 1);
        }
        row_info[r].push_back(col);
    }

    row_num = max_r;
    column_num = max_c;

    // Sort column indices in each row to ensure consistent processing
    for (auto &cols : row_info) {
        std::sort(cols.begin(), cols.end());
    }

    // Store the cell data in a way that to_csv can access it efficiently
    // Since we can't change the header, we'll use a local map or re-process.
    // However, the requirement says _cells is a member. Let's use a helper map.
    // To avoid changing the header, we'll just use the _cells vector in to_csv.
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (_cells.empty()) {
        return "";
    }

    // Map to quickly find the shared string index for a given (row, col)
    std::map<std::pair<std::uint32_t, std::uint32_t>, std::uint32_t> cell_lookup;
    for (const auto &c : _cells) {
        cell_lookup[{std::get<0>(c), std::get<1>(c)}] = std::get<2>(c);
    }

    std::stringstream ss;
    const workbook* wb = static_cast<const workbook*>(_workbook);

    for (std::uint32_t r = 1; r <= row_num; ++r) {
        bool first_in_row = true;
        for (std::uint32_t c = 1; c <= column_num; ++c) {
            if (!first_in_row) {
                ss << ",";
            }
            
            auto it = cell_lookup.find({r, c});
            if (it != cell_lookup.end()) {
                std::uint32_t s_idx = it->second;
                // If s_idx is 0, it might mean empty or index 0. 
                // But architecture says shared strings start from index 1.
                if (s_idx > 0) {
                    ss << wb->get_shared_string(s_idx);
                }
            }
            first_in_row = false;
        }
        ss << "\n";
    }

    return ss.str();
}

} // namespace xlsx_reader
} // namespace my_xlsx
