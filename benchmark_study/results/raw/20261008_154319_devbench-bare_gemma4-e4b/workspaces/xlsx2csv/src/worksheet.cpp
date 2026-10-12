#include "../include/worksheet.h"
#include "../include/workbook.h"
#include "../include/utils.h"
#include <sstream>
#include <iostream>

worksheet::worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& sheet_name, workbook* workbook_ptr)
    : _name(sheet_name), _sheet_id(sheet_id), _workbook(workbook_ptr), _cells(cells) {}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    std::stringstream csv_stream;
    
    // Determine the maximum row and column needed for CSV structure
    std::uint32_t max_row = 0;
    std::uint32_t max_col = 0;

    for (const auto& cell_tuple : _cells) {
        // cell: std::tuple<row_id, column_id, shared_string_id>
        std::uint32_t row_id = std::get<0>(cell_tuple);
        std::uint32_t col_id = std::get<1>(cell_tuple);
        
        if (row_id > max_row) max_row = row_id;
        if (col_id > max_col) max_col = col_id;
    }

    // CSV Header (optional, but good practice if we knew column names, here we just rely on data)
    // Since we don't have explicit headers, we just iterate through cells in order.

    // To maintain row/column integrity for CSV output, we need to iterate over all possible cells
    // up to max_row and max_col, filling in empty cells if necessary, though the input _cells
    // should ideally contain all populated cells.

    // A simpler approach matching the requirement: iterate over the provided cells and format them.
    // However, to ensure correct CSV structure (rows), we must group cells by row.

    std::vector<std::vector<std::string>> row_data(max_row + 1);
    
    for (const auto& cell_tuple : _cells) {
        std::uint32_t row_id = std::get<0>(cell_tuple);
        std::uint32_t col_id = std::get<1>(cell_tuple);
        std::uint32_t ss_id = std::get<2>(cell_tuple);

        // Get the shared string value using the workbook pointer
        std::string value = _workbook->get_shared_string(ss_id);
        
        // Append value to the correct row
        row_data[row_id].push_back(value);
    }

    // Output CSV row by row
    for (std::uint32_t r = 1; r <= max_row; ++r) {
        std::string row_string = "";
        
        // We need to ensure columns are ordered correctly. Since _cells is not guaranteed to be sorted
        // by row then column, we must reconstruct the row based on column index.
        std::vector<std::string> current_row_values(max_col + 1, ""); // +1 for 1-based indexing
        
        // Re-iterate over cells to populate the row structure correctly based on column index
        for (const auto& cell_tuple : _cells) {
            std::uint32_t cell_row_id = std::get<0>(cell_tuple);
            std::uint32_t cell_col_id = std::get<1>(cell_tuple);
            std::uint32_t ss_id = std::get<2>(cell_tuple);

            if (cell_row_id == r) {
                std::string value = _workbook->get_shared_string(ss_id);
                current_row_values[cell_col_id] = value;
            }
        }

        // Build the CSV line from the ordered column values
        for (std::uint32_t c = 1; c <= max_col; ++c) {
            std::string cell_content = current_row_values[c];
            // Basic CSV escaping: wrap in quotes if it contains comma or newline (though not strictly required by PRD, it's safe)
            if (cell_content.find(',') != std::string::npos || cell_content.find('\n') != std::string::npos) {
                cell_content = "\"" + cell_content + "\"";
            }
            row_string += cell_content;
            if (c < max_col) {
                row_string += ",";
            }
        }
        
        csv_stream << row_string << "\n";
    }

    return csv_stream.str();
}
