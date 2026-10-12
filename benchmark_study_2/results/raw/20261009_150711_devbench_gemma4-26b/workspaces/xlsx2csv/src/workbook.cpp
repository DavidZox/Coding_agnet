#include "workbook.h"
#include "archive.h"
#include "worksheet.h"
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
        // rel is sheet_desc: tuple<name, id, rId>
        std::string name = std::get<0>(rel);
        std::uint32_t id = std::get<1>(rel);
        std::string rId = std::get<2>(rel);

        std::vector<cell> cells = get_sheet_cells(id);
        worksheets.push_back(std::make_unique<worksheet>(cells, id, name, this));
    }
}

std::vector<cell> workbook::get_sheet_cells(std::uint32_t sheet_id) {
    std::vector<cell> cells;
    
    // Find the rId corresponding to the sheet_id from sheet_relations
    std::string rId = "";
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == sheet_id) {
            rId = std::get<2>(rel);
            break;
        }
    }
    
    if (rId.empty()) return cells;

    auto xml_doc_ptr = my_archive->get_sheet_xml(rId);
    if (!xml_doc_ptr) return cells;

    tinyxml2::XMLDocument* doc = xml_doc_ptr.get();
    tinyxml2::XMLElement* root = doc->RootElement();
    if (!root) return cells;

    tinyxml2::XMLElement* sheetData = root->FirstChildElement("sheetData");
    if (!sheetData) return cells;

    for (tinyxml2::XMLElement* row_el = sheetData->FirstChildElement("row"); row_el != nullptr; row_el = row_el->NextSiblingElement("row")) {
        for (tinyxml2::XMLElement* c_el = row_el->FirstChildElement("c"); c_el != nullptr; c_el = c_el->NextSiblingElement("c")) {
            const char* ref_attr = c_el->Attribute("r");
            if (!ref_attr) continue;

            std::string ref_str = ref_attr;
            std::string coords_str = string_to_row_column(ref_str);
            
            // Parse "row,col" string
            size_t comma_pos = coords_str.find(',');
            std::uint32_t row = 0;
            std::uint32_t col = 0;
            if (comma_pos != std::string::npos) {
                row = std::stoul(coords_str.substr(0, comma_pos));
                col = std::stoul(coords_str.substr(comma_pos + 1));
            }

            std::uint32_t ss_idx = 0;
            tinyxml2::XMLElement* v_el = c_el->FirstChildElement("v");
            if (v_el) {
                const char* val = v_el->GetText();
                if (val) {
                    ss_idx = static_cast<std::uint32_t>(std::stoul(val));
                }
            }
            
            // cell: tuple<row, col, ss_idx>
            cells.emplace_back(row, col, ss_idx);
        }
    }
    return cells;
}

std::string workbook::get_shared_string(std::uint32_t idx) const {
    // Note: shared_string is 1-indexed in the requirement logic, 
    // but the vector is 0-indexed. If idx 1 maps to vector[0], 
    // we must handle the offset. However, the requirement says 
    // "shared strings are started from index 1, rather than 0".
    // This usually means the first string is at index 1.
    if (idx > 0 && idx <= shared_string.size()) {
        return shared_string[idx - 1];
    }
    return "";
}

void workbook::write_to_csv(std::string output_path) {
    if (!fs::exists(output_path)) {
        fs::create_directories(output_path);
    }

    for (const auto& ws : worksheets) {
        std::string filename = ws->get_name() + ".csv";
        fs::path full_path = fs::path(output_path) / filename;
        
        std::ofstream out(full_path);
        if (out.is_open()) {
            out << ws->to_csv();
            out.close();
        }
    }
}
