#include "workbook.h"
#include "worksheet.h"
#include "archive.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <filesystem>

namespace fs = std::filesystem;

workbook::workbook(const std::string& filename) {
    my_archive = std::make_shared<archive>(filename);
    shared_string = my_archive->get_shared_strings();
    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& rel : sheet_relations) {
        const std::string& name = std::get<0>(rel);
        std::uint32_t id = std::get<1>(rel);
        std::string rId = std::get<2>(rel);

        // In XLSX, the sheet_id in sheet_relations is used to identify the sheet.
        // We need to find the cells for this specific sheet.
        std::vector<cell> cells = get_sheet_cells(id);
        
        worksheets.push_back(std::make_unique<worksheet>(cells, id, name, this));
    }
}

std::vector<cell> workbook::get_sheet_cells(std::uint32_t sheet_id) {
    std::string sheet_path;
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == sheet_id) {
            sheet_path = std::get<2>(rel);
            break;
        }
    }

    std::vector<cell> cells;
    if (sheet_path.empty()) return cells;

    auto xml_doc = my_archive->get_sheet_xml(sheet_path);
    if (!xml_doc) return cells;

    tinyxml2::XMLElement* root = xml_doc->FirstChildElement("worksheet");
    if (!root) return cells;

    tinyxml2::XMLElement* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return cells;

    for (tinyxml2::XMLElement* c_elem = sheet_data->FirstChildElement("c"); 
         c_elem != nullptr; 
         c_elem = c_elem->NextSiblingElement("c")) {
        
        const char* r_attr = c_elem->Attribute("r");
        if (!r_attr) continue;

        std::string r_str(r_attr);
        auto [row, col] = string_to_row_column(r_str);

        // Parse type attribute to check if it's a shared string
        const char* t_attr = c_elem->Attribute("t");
        bool is_shared_string = (t_attr != nullptr && std::string(t_attr) == "s");

        tinyxml2::XMLElement* v_elem = c_elem->FirstChildElement("v");
        if (!v_elem) continue;

        const char* v_text = v_elem->GetText();
        if (!v_text) continue;

        std::uint32_t val = static_cast<std::uint32_t>(std::stoul(v_text));

        if (is_shared_string) {
            cells.push_back(std::make_tuple(row, col, val));
        } else {
            // For non-shared strings (numbers), we use 0 as the index 
            // as per the cell definition (row, col, shared_string_idx)
            cells.push_back(std::make_tuple(row, col, 0));
        }
    }

    return cells;
}

std::string workbook::get_shared_string(std::uint32_t idx) const {
    if (idx < shared_string.size()) {
        return shared_string[idx];
    }
    return "";
}

void workbook::write_to_csv(std::string output_path) {
    // Ensure output directory exists
    if (!fs::exists(output_path)) {
        fs::create_directories(output_path);
    }

    for (const auto& ws : worksheets) {
        std::string filename = output_path + "/" + ws->get_name() + ".csv";
        std::ofstream file(filename);
        if (file.is_open()) {
            file << ws->to_csv();
            file.close();
        }
    }
}
