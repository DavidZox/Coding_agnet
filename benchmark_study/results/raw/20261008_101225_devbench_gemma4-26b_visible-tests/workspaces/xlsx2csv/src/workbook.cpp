#include "workbook.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;

workbook::workbook(const std::string& filename) {
    my_archive = std::make_shared<my_xlsx::xlsx_reader::archive>(filename);
    
    // Shared strings are 1-indexed in the requirement (index 1 is the first string)
    // We add a dummy empty string at index 0 to make it 1-indexed easily.
    shared_string.push_back(""); 
    std::vector<std::string> ss_list = my_archive->get_shared_strings();
    for (const auto& s : ss_list) {
        shared_string.push_back(s);
    }

    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& rel : sheet_relations) {
        // rel is tuple<name, id, rId>
        std::uint32_t sheet_id = std::get<1>(rel);
        get_sheet_cells(sheet_id);
    }
}

void workbook::get_sheet_cells(std::uint32_t sheet_id) {
    // Find the relation ID for this sheet_id
    std::string r_id;
    std::string sheet_name;
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == sheet_id) {
            sheet_name = std::get<0>(rel);
            r_id = std::get<2>(rel);
            break;
        }
    }

    if (r_id.empty()) return;

    auto xml_doc = my_archive->get_sheet_xml(r_id);
    if (!xml_doc) return;

    std::vector<my_xlsx::xlsx_reader::cell> cells;
    auto* root = xml_doc->FirstChildElement("worksheet");
    if (!root) return;

    auto* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return;

    for (auto* row_node = sheet_data->FirstChildElement("row"); row_node != nullptr; row_node = row_node->NextSiblingElement("row")) {
        for (auto* cell_node = row_node->FirstChildElement("c"); cell_node != nullptr; cell_node = cell_node->NextSiblingElement("c")) {
            std::string c_ref = cell_node->Attribute("r");
            auto [row_val, col_val] = my_xlsx::xlsx_reader::string_to_row_column(c_ref);
            
            std::uint32_t s_idx = 0;
            auto* v_node = cell_node->FirstChildElement("v");
            if (v_node && v_node->GetText()) {
                // In XLSX, shared string index in <v> is 0-indexed in XML, 
                // but our workbook.shared_string is 1-indexed.
                // So we add 1 to the value found in XML.
                s_idx = static_cast<std::uint32_t>(std::stoul(v_node->GetText())) + 1;
            }

            // cell is tuple<row, col, shared_string_idx>
            // Note: The requirement says cell is (row, col, shared_string_id)
            // We use r_idx to ensure the row index is correctly captured if needed, 
            // but the requirement for cell tuple is (row, col, shared_string_id).
            // Since string_to_row_column provides row_val, we use that.
            cells.push_back(std::make_tuple(row_val, col_val, s_idx));
        }
    }

    worksheets.push_back(std::make_unique<worksheet>(cells, sheet_id, sheet_name, this));
}

std::string workbook::get_shared_string(std::uint32_t index) const {
    if (index > 0 && index < static_cast<std::uint32_t>(shared_string.size())) {
        return shared_string[index];
    }
    return "";
}

void workbook::write_to_csv(const std::string& output_path) {
    fs::path out_dir(output_path);
    if (!fs::exists(out_dir)) {
        fs::create_directories(out_dir);
    }

    for (const auto& ws : worksheets) {
        std::string csv_content = ws->to_csv();
        std::string filename = ws->get_name() + ".csv";
        fs::path file_path = out_dir / filename;

        std::ofstream out_file(file_path);
        if (out_file.is_open()) {
            out_file << csv_content;
            out_file.close();
        }
    }
}
