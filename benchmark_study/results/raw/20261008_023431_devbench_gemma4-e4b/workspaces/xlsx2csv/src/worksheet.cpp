#include "worksheet.h"
#include "../include/workbook.h"
#include <sstream>
#include <iostream>
#include <optional>
#include <tuple>
#include <vector>
#include <string>

Worksheet::Worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, Workbook* workbook)
    : _cells(cells), _sheet_id(sheet_id), _name(name), _workbook(workbook) {}

std::string Worksheet::get_name() const {
    return _name;
}

std::string Worksheet::to_csv() const {
    std::stringstream csv_stream;
    
    // Determine the maximum row and column indices to correctly size the output
    std::uint32_t max_row = 0;
    std::uint32_t max_col = 0;

    for (const auto& cell : _cells) {
        std::uint32_t row_id = std::get<0>(cell);
        std::uint32_t col_id = std::get<1>(cell);
        
        if (row_id > max_row) {
            max_row = row_id;
        }
        if (col_id > max_col) {
            max_col = col_id;
        }
    }

    // Iterate through all potential rows and columns up to the maximum found
    for (std::uint32_t r = 1; r <= max_row; ++r) {
        std::vector<std::string> row_data;
        for (std::uint32_t c = 1; c <= max_col; ++c) {
            // Find the cell corresponding to (r, c)
            std::optional<std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>> found_cell;
            for (const auto& cell : _cells) {
                if (std::get<0>(cell) == r && std::get<1>(cell) == c) {
                    found_cell = cell;
                    break;
                }
            }

            std::string cell_value = "";
            if (found_cell.has_value()) {
                std::uint32_t ss_idx = std::get<2>(found_cell.value());
                // Use the workbook pointer to get the actual string value
                if (_workbook) {
                    cell_value = _workbook->get_shared_string(ss_idx);
                }
            }
            
            // CSV formatting: enclose in quotes if it contains comma or newline, though simple string output is expected here.
            // For simplicity matching typical CSV output, we just append the value.
            row_data.push_back(cell_value);
        }

        // Join cells in the row with commas
        for (size_t i = 0; i < row_data.size(); ++i) {
            csv_stream << row_data[i];
            if (i < row_data.size() - 1) {
                csv_stream << ",";
            }
        }
        csv_stream << "\n";
    }

    return csv_stream.str();
}
