#include "workbook.h"
#include "archive.h"
#include "worksheet.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <memory>
#include <vector>
#include <string>
#include <tuple>

Workbook::Workbook(const std::string& xlsx_filename) :
    my_archive(std::make_shared<Archive>(xlsx_filename)),
    sheet_relations(my_archive->get_sheet_relations()),
    shared_string(my_archive->get_shared_strings())
{
    // Initialize worksheets
    for (const auto& sheet_desc : sheet_relations) {
        const std::string& sheet_name = std::get<0>(sheet_desc);
        std::uint32_t sheet_id = std::get<1>(sheet_desc);
        std::string sheet_relation_id = std::get<2>(sheet_desc);

        // Get sheet XML
        std::shared_ptr<tinyxml2::XMLDocument> sheet_xml = my_archive->get_sheet_xml(sheet_relation_id);

        if (sheet_xml) {
            // Get cells for the sheet
            std::vector<cell> cells = get_sheet_cells(sheet_id, sheet_xml);

            // Create worksheet instance
            // Note: The constructor of Worksheet expects a pointer to Workbook,
            // which we provide 'this' for.
            worksheets.push_back(std::make_unique<Worksheet>(
                cells, sheet_id, sheet_name, this
            ));
        } else {
            std::cerr << "Warning: Could not retrieve XML for sheet: " << sheet_name << std::endl;
        }
    }
}

std::string Workbook::get_shared_string(std::uint32_t index) const {
    // Shared strings are 1-indexed in the XLSX structure, but stored in a 0-indexed vector.
    if (index > 0 && index <= shared_string.size()) {
        return shared_string[index - 1];
    }
    return ""; // Return empty string if index is out of bounds
}

std::vector<cell> Workbook::get_sheet_cells(std::uint32_t sheet_id, std::shared_ptr<tinyxml2::XMLDocument> sheet_xml) const {
    std::vector<cell> cells;
    if (!sheet_xml) {
        return cells;
    }

    // Implementation based on the requirement to extract cells from sheet_xml.
    // This requires parsing the XML structure which is assumed to be available in sheet_xml.
    // Since the exact XML structure is not provided, we must simulate the parsing logic
    // based on the expected output: vector<cell> where cell = tuple<row_id, col_id, ss_id>.

    tinyxml2::XMLElement* sheet_element = sheet_xml->FirstChildElement();
    if (!sheet_element) {
        return cells;
    }

    // Iterate through rows
    for (tinyxml2::XMLElement* row_element = sheet_element->FirstChildElement("row"); row_element != nullptr; row_element = row_element->NextSiblingElement("row")) {
        std::uint32_t row_id = 0;
        // Assuming row ID is stored somewhere or derived, for simplicity we use a counter if not explicitly found
        // In a real scenario, row ID would be parsed from the row element attributes.
        // For this implementation, we rely on the structure provided by the caller/archive.
        // Since the UML suggests cell tuple is (row_id, col_id, ss_id), we need to find row_id.
        // We will use a simple counter for row_id if not explicitly available in the XML structure we are simulating.
        // However, to adhere strictly to the tuple definition, we must assume row_id can be found.
        // Let's assume the row element has an attribute 'r' for row ID.
        if (row_element->QueryAttribute("r", &row_id) != tinyxml2::XML_SUCCESS) {
             // If attribute 'r' is missing, we skip or use a placeholder.
             // For robustness, we'll skip if we can't determine the row ID.
             continue;
        }

        // Iterate through cells in the row
        for (tinyxml2::XMLElement* cell_element = row_element->FirstChildElement("c"); cell_element != nullptr; cell_element = cell_element->NextSiblingElement("c")) {
            std::uint32_t col_id = 0;
            // Assuming cell element has an attribute 'c' for column ID.
            if (cell_element->QueryAttribute("c", &col_id) != tinyxml2::XML_SUCCESS) {
                continue;
            }

            std::uint32_t ss_id = 0;
            // Assuming the shared string ID is stored in an attribute 't' or similar, 
            // or derived from the cell content if it's not a shared string reference.
            // Based on the cell tuple definition (row_id, col_id, shared_string_id), 
            // we assume the shared string ID is available, perhaps via an attribute 'ss' or 't'.
            if (cell_element->QueryAttribute("ss", &ss_id) != tinyxml2::XML_SUCCESS) {
                // If ss_id is not found, we might treat it as 0 or skip, depending on data integrity rules.
                // We assume it must be present for a valid cell entry in this context.
                continue;
            }

            // Add the cell tuple: (row_id, col_id, ss_id)
            cells.emplace_back(row_id, col_id, ss_id);
        }
    }

    return cells;
}

void Workbook::write_to_csv(const std::string& output_path) {
    bool success = true;
    for (const auto& worksheet_ptr : worksheets) {
        // 1. Get CSV data string from Worksheet
        std::string csv_data = worksheet_ptr->to_csv();

        // 2. Determine output filename (Sheet Name + .csv)
        std::string sheet_name = worksheet_ptr->get_name();
        std::string filename = sheet_name + ".csv";
        std::string full_path = output_path + "/" + filename;

        // 3. Write to file
        std::ofstream outfile(full_path);
        if (outfile.is_open()) {
            outfile << csv_data;
            outfile.close();
        } else {
            std::cerr << "Error: Could not open file for writing: " << full_path << std::endl;
            success = false;
        }
    }

    if (success) {
        std::cout << "Conversion successful. CSV files generated." << std::endl;
    } else {
        // If any file failed to write, we might want to indicate failure, 
        // though the PRD only specifies success message on successful conversion.
        // For robustness, we rely on the loop's internal error reporting.
    }
}
