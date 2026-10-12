#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <algorithm>
#include <map>

worksheet::worksheet(const std::vector<cell> &cells, std::uint32_t sheet_id, const std::string &name, const void *workbook)
    : _name(name), _sheet_id(sheet_id), _workbook(workbook), _cells(cells), row_num(0), column_num(0) {
    
    if (_cells.empty()) {
        return;
    }

    // row_info[r] will store a list of column indices present in row r
    // We use a map to handle sparse rows and then convert to vector
    std::map<std::uint32_t, std::map<std::uint32_t, std::uint32_t>> sparse_rows;

    for (const auto &c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t val_idx = std::get<2>(c);

        // Adjusting to 0-indexed for internal storage if necessary, 
        // but the spec says cell is (row, col, val_idx). 
        // Let's assume row and col in cell tuple are 1-indexed as per typical Excel logic.
        // However, to be safe and consistent with the logic of "row_info[r]", 
        // we'll treat the tuple values as the actual indices.
        
        sparse_rows[r][col] = val_idx;

        if (r > row_num) row_num = r;
        if (col > column_num) column_num = col;
    }

    // Initialize row_info. Since row_num is the max index, size should be row_num + 1
    row_info.resize(row_num + 1);
    for (auto const& [r, cols] : sparse_rows) {
        for (auto const& [col, val] : cols) {
            row_info[r].push_back(col);
        }
        // Sort column indices for each row to ensure correct CSV order
        std::sort(row_info[r].begin(), row_info[r].end());
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (_cells.empty()) {
        return "";
    }

    std::stringstream ss;
    const workbook* wb = static_cast<const workbook*>(_workbook);

    // Iterate through all rows from 1 to row_num (assuming 1-based indexing from Excel)
    // If the input uses 0-based, this still works if we start from 0.
    // Based on the UML/Spec, we'll iterate through the rows that actually have data.
    
    // To handle the CSV correctly, we need to know the max column index for each row
    // to ensure we don't skip columns, but CSV is usually row-by-row.
    // A standard way is to iterate row by row, and for each row, iterate column by column.

    // Find the actual range of rows present in the data
    std::map<std::uint32_t, std::map<std::uint32_t, std::uint32_t>> data;
    std::uint32_t max_r = 0;
    std::uint32_t max_c = 0;

    for (const auto &c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t val_idx = std::get<2>(c);
        data[r][col] = val_idx;
        if (r > max_r) max_r = r;
        if (col > max_c) max_c = col;
    }

    for (std::uint32_t r = 1; r <= max_r; ++r) {
        if (data.find(r) == data.end()) continue; // Skip empty rows if any

        for (std::uint32_t c = 1; c <= max_c; ++c) {
            if (data[r].count(c)) {
                std::uint32_t val_idx = data[r][c];
                // If val_idx is 0, it might mean empty or index 0. 
                // But shared strings start from index 1 per spec.
                if (val_idx > 0 && wb) {
                    ss << wb->get_shared_string(val_idx);
                }
            }
            
            if (c < max_c) {
                ss << ",";
            }
        }
        ss << "\n";
    }

    return ss.str();
}
