#include "workbook.h"
#include "archive.h"
#include "worksheet.h"
#include "utils.h"
#include <fstream>
#include <iostream>
#include <filesystem>
#include <tinyxml2.h>

namespace fs = std::filesystem;

workbook::workbook(const std::string& filename) {
    my_archive = std::make_shared<archive>(filename);
    shared_string = my_archive->get_shared_strings();
    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& rel : sheet_relations) {
        std::uint32_t sheet_id = std::get<1>(rel);
        std::string sheet_path = std::get<2>(rel);
        
        std::vector<cell> cells = get_sheet_cells(sheet_id);
        std::string sheet_name = std::get<0>(rel);
        
        worksheets.push_back(std::make_unique<worksheet>(cells, sheet_id, sheet_name, this));
    }
}

std::vector<cell> workbook::get_sheet_cells(std::uint32_t sheet_id) {
    std::vector<cell> cells;
    std::string sheet_path;
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == sheet_id) {
            sheet_path = std::get<2>(rel);
            break;
        }
    }
    
    if (sheet_path.empty()) return cells;

    auto xml_doc = my_archive->get_sheet_xml(sheet_path);
    if (!xml_doc) return cells;

    tinyxml2::XMLElement* root = xml_doc->FirstChildElement("worksheet");
    if (!root) return cells;

    tinyxml2::XMLElement* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return cells;

    for (tinyxml2::XMLElement* row_el = sheet_data->FirstChildElement("row"); row_el != nullptr; row_el = row_el->NextSiblingElement("row")) {
        for (tinyxml2::XMLElement* cell_el = row_el->FirstChildElement("c"); cell_el != nullptr; cell_el = cell_el->NextSiblingElement("c")) {
            const char* r_attr = cell_el->Attribute("r");
            if (!r_attr) continue;

            std::string r_col_str = strip(r_attr);
            auto [row_idx, col_idx] = string_to_row_column(r_col_str);

            std::uint32_t s_idx = 0;
            const char* t_attr = cell_el->Attribute("t");
            if (t_attr && std::string(t_attr) == "s") {
                tinyxml2::XMLElement* v_el = cell_el->FirstChildElement("v");
                if (v_el && v_el->GetText()) {
                    s_idx = static_cast<std::uint32_t>(std::stoul(v_el->GetText()));
                }
            }
            
            cells.emplace_back(row_idx, col_idx, s_idx);
        }
    }
    return cells;
}

std::string workbook::get_shared_string(std::uint32_t i) const {
    if (i > 0 && i <= shared_string.size()) {
        return shared_string[i - 1];
    }
    return "";
}

void workbook::write_to_csv(std::string output_path) {
    fs::path out_dir(output_path);
    if (!fs::exists(out_dir)) {
        fs::create_directories(out_dir);
    }

    for (const auto& ws : worksheets) {
        std::string filename = ws->get_name() + ".csv";
        fs::path file_path = out_dir / filename;
        
        std::ofstream ofs(file_path);
        if (ofs.is_open()) {
            ofs << ws->to_csv();
            ofs.close();
        }
    }
}
