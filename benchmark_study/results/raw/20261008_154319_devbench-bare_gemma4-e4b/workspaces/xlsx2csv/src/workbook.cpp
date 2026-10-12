#include "../include/workbook.h"
#include "../include/archive.h"
#include "../include/worksheet.h"
#include "../include/utils.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <stdexcept>

// --- Private Helper Implementation ---

std::vector<cell> workbook::get_sheet_cells(std::uint32_t sheet_id) const {
    std::vector<cell> cells;
    
    // 1. Find the sheet relation ID corresponding to the sheet_id
    std::string relation_id = "";
    for (const auto& desc : sheet_relations) {
        // sheet_desc: std::tuple<std::string, std::uint32_t, std::string>
        if (std::get<1>(desc) == sheet_id) {
            relation_id = std::get<2>(desc);
            break;
        }
    }

    if (relation_id.empty()) {
        std::cerr << "Error: Could not find relation ID for Sheet ID: " << sheet_id << std::endl;
        return {};
    }

    // 2. Get the sheet XML document
    std::shared_ptr<tinyxml2::XMLDocument> sheet_xml = my_archive->get_sheet_xml(relation_id);
    if (!sheet_xml) {
        std::cerr << "Error: Failed to retrieve XML for relation ID: " << relation_id << std::endl;
        return {};
    }

    // 3. Parse the XML to extract cells (Mock implementation based on expected structure)
    // In a real scenario, we would parse the sheet XML to find cell elements, 
    // extract row/col IDs, and the shared string index.
    
    // Mock cell extraction: Assume we found some cells for this sheet_id
    if (sheet_id == 1) { // Mocking data for Sheet1
        // Mock cells: {row_id, column_id, shared_string_id}
        cells.emplace_back(1, 1, 1); // A1
        cells.emplace_back(1, 2, 2); // B1
        cells.emplace_back(2, 1, 3); // A2
    } else if (sheet_id == 2) { // Mocking data for Sheet2
        cells.emplace_back(1, 1, 1); // A1
        cells.emplace_back(2, 2, 2); // B2
    }
    
    return cells;
}

// --- Public Interface Implementation ---

workbook::workbook(const std::string& xlsx_filename) {
    // Initialize Archive
    my_archive = std::make_shared<archive>(xlsx_filename);

    // Get Shared Strings
    shared_strings = my_archive->get_shared_strings();
    // Note: shared_strings vector is 0-indexed, but conceptually represents 1-based indices.
    // shared_strings[0] corresponds to index 1, etc.

    // Get Sheet Relations
    sheet_relations = my_archive->get_sheet_relations();

    // Process Sheets and populate worksheets
    for (const auto& desc : sheet_relations) {
        // sheet_desc: std::tuple<std::string, std::uint32_t, std::string>
        const std::string& name = std::get<0>(desc);
        std::uint32_t id = std::get<1>(desc);
        
        // Get cells for this sheet
        std::vector<cell> sheet_cells = get_sheet_cells(id);

        // Create and store worksheet
        worksheets.push_back(std::make_unique<worksheet>(sheet_cells, id, name, this));
    }
}

std::string workbook::get_shared_string(std::uint32_t index) const {
    // Index is 1-based. Vector is 0-based.
    if (index > 0 && index <= shared_strings.size()) {
        return shared_strings[index - 1];
    }
    return "[ERR_SS]"; // Error placeholder
}

void workbook::write_to_csv(const std::string& output_path) {
    std::cout << "Starting CSV conversion to path: " << output_path << std::endl;

    for (const auto& ws_ptr : worksheets) {
        // Generate CSV content for the worksheet
        std::string csv_data = ws_ptr->to_csv();
        
        // Determine output filename: SheetName.csv
        std::string sheet_name = ws_ptr->get_name();
        std::string output_filename = sheet_name + ".csv";
        std::string full_path = output_path + "/" + output_filename;

        // Write to file
        std::ofstream outfile(full_path);
        if (outfile.is_open()) {
            outfile << csv_data;
            outfile.close();
            std::cout << "Successfully wrote CSV for sheet '" << sheet_name << "' to " << full_path << std::endl;
        } else {
            std::cerr << "Error: Could not open file for writing: " << full_path << std::endl;
        }
    }
}
