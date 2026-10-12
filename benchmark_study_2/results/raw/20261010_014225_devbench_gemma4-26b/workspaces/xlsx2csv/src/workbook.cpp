#include "workbook.h"
#include "worksheet.h"
#include "archive.h"
#include "utils.h"
#include <fstream>
#include <iostream>
#include <filesystem>

namespace fs = std::filesystem;

workbook::workbook(const std::string& filename) {
    my_archive = std::make_shared<archive>(filename);
    shared_string = my_archive->get_shared_strings();
    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& rel : sheet_relations) {
        // rel is sheet_desc: tuple<name, id, path>
        std::uint32_t sheet_id = std::get<1>(rel);
        std::string sheet_name = std::get<0>(rel);
        
        get_sheet_cells(sheet_id);
        worksheets.push_back(std::make_unique<worksheet>(all_cells[sheet_id], sheet_id, sheet_name, this));
    }
}

void workbook::get_sheet_cells(std::uint32_t sheet_id) {
    std::string sheet_path;
    std::string sheet_name;
    bool found = false;

    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == sheet_id) {
            sheet_name = std::get<0>(rel);
            sheet_path = std::get<2>(rel);
            found = true;
            break;
        }
    }

    if (!found) return;

    auto xml_doc = my_archive->get_sheet_xml(sheet_path);
    if (!xml_doc) return;

    tinyxml2::XMLElement* root = xml_doc->FirstChildElement("worksheet");
    if (!root) return;

    tinyxml2::XMLElement* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return;

    std::vector<cell> cells;
    for (tinyxml2::XMLElement* row_el = sheet_data->FirstChildElement("row"); row_el != nullptr; row_el = row_el->NextSiblingElement("row")) {
        for (tinyxml2::XMLElement* cell_el = row_el->FirstChildElement("c"); cell_el != nullptr; cell_el = cell_el->NextSiblingElement("c")) {
            const char* r_attr = cell_el->Attribute("r");
            if (!r_attr) continue;

            std::string r_col_str = r_attr;
            std::pair<std::uint32_t, std::uint32_t> coords = string_to_row_column(r_col_str);
            
            std::uint32_t row_idx = coords.first;
            std::uint32_t col_idx = coords.second;

            std::uint32_t val_idx = 0;
            const char* type_attr = cell_el->Attribute("t");
            
            tinyxml2::XMLElement* v_el = cell_el->FirstChildElement("v");
            if (v_el && v_el->GetText()) {
                std::string v_text = v_el->GetText();
                if (type_attr && std::string(type_attr) == "s") {
                    // Shared string
                    val_idx = std::stoul(v_text);
                } else {
                    // Number or other (treat as 0 index for simplicity if not shared, 
                    // but the cell tuple stores the value in the 3rd element)
                    // However, the requirement says cell is (row, col, shared_string_idx).
                    // For numbers, we'll store it as a special index or 
                    // handle it in worksheet. Let's store the numeric value in the 3rd element 
                    // and let worksheet handle it.
                    val_idx = std::stoul(v_text); 
                }
            }
            cells.push_back(std::make_tuple(row_idx, col_idx, val_idx));
        }
    }
    all_cells[sheet_id] = cells;
}

std::string workbook::get_shared_string(std::uint32_t i) const {
    if (i > 0 && i < (std::uint32_t)shared_string.size()) {
        return shared_string[i];
    }
    return "";
}

void workbook::write_to_csv(std::string output_path) {
    fs::create_directories(output_path);

    for (const auto& ws_ptr : worksheets) {
        std::string sheet_name = ws_ptr->get_name();
        // Replace characters that might be invalid in filenames if necessary, 
        // but here we follow the requirement: "named after its corresponding sheet name".
        std::string file_name = sheet_name + ".csv";
        fs::path full_path = fs::path(output_path) / file_name;

        std::ofstream out_file(full_path);
        if (out_file.is_open()) {
            out_file << ws_ptr->to_csv();
            out_file.close();
        }
    }
}
