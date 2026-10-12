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
    
    // Shared strings are 1-indexed in the requirement (index 1 is the first string)
    // We add a dummy at index 0 to make it 1-indexed.
    shared_string.push_back(""); 
    std::vector<std::string> ss_list = my_archive->get_shared_strings();
    for (const auto& s : ss_list) {
        shared_string.push_back(s);
    }

    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& rel : sheet_relations) {
        std::uint32_t sheet_id = std::get<1>(rel);
        std::string sheet_name = std::get<0>(rel);
        
        std::vector<cell> cells = get_sheet_cells(sheet_id);
        worksheets.push_back(std::make_unique<worksheet>(cells, sheet_id, sheet_name, this));
    }
}

std::vector<cell> workbook::get_sheet_cells(std::uint32_t sheet_id) {
    std::string relation_id;
    
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == sheet_id) {
            relation_id = std::get<2>(rel);
            break;
        }
    }

    auto xml_doc = my_archive->get_sheet_xml(relation_id);
    std::vector<cell> cells;

    if (!xml_doc) return cells;

    tinyxml2::XMLElement* root = xml_doc->FirstChildElement("worksheet");
    if (!root) return cells;

    tinyxml2::XMLElement* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return cells;

    for (tinyxml2::XMLElement* c_elem = sheet_data->FirstChildElement("c"); c_elem != nullptr; c_elem = c_elem->NextSiblingElement("c")) {
        const char* r_attr = c_elem->Attribute("r");
        if (!r_attr) continue;

        std::string r_str = r_attr;
        auto [row, col] = string_to_row_column(r_str);

        std::uint32_t ss_idx = 0;
        const char* t_attr = c_elem->Attribute("t");
        
        tinyxml2::XMLElement* v_elem = c_elem->FirstChildElement("v");
        if (!v_elem) continue;
        
        const char* v_text = v_elem->GetText();
        if (!v_text) continue;

        if (t_attr && std::string(t_attr) == "s") {
            ss_idx = std::stoul(v_text);
        } else {
            // If it's not a shared string, we treat the value as a literal 
            // but the cell type 'cell' tuple expects (row, col, ss_idx).
            // For simplicity in this specific task, we'll treat non-shared strings as a new entry in shared_string.
            shared_string.push_back(std::string(v_text));
            ss_idx = shared_string.size() - 1;
        }

        cells.push_back(std::make_tuple(row, col, ss_idx));
    }

    return cells;
}

std::string workbook::get_shared_string(std::uint32_t i) const {
    if (i < shared_string.size()) {
        return shared_string[i];
    }
    return "";
}

void workbook::write_to_csv(std::string output_path) {
    fs::path out_dir(output_path);
    if (!fs::exists(out_dir)) {
        fs::create_directories(out_dir);
    }

    for (const auto& ws : worksheets) {
        std::string sheet_name = ws->get_name();
        fs::path file_path = out_dir / (sheet_name + ".csv");
        
        std::ofstream ofs(file_path);
        if (ofs.is_open()) {
            ofs << ws->to_csv();
            ofs.close();
        }
    }
}
