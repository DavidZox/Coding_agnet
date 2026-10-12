#include "workbook.h"
#include "archive.h"
#include "worksheet.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;

namespace my_xlsx {
namespace xlsx_reader {

workbook::workbook(const std::string& filename) {
    my_archive = std::make_shared<archive>(filename);
    
    // Shared strings are 1-indexed in the requirement (index 1 is first string)
    // We add a dummy empty string at index 0 to make it 1-indexed easily
    shared_string.push_back(""); 
    std::vector<std::string> ss_list = my_archive->get_shared_strings();
    for (const auto& s : ss_list) {
        shared_string.push_back(s);
    }

    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& rel : sheet_relations) {
        // rel is tuple<name, id, rId>
        std::uint32_t sheet_id = std::get<1>(rel);
        std::string sheet_name = std::get<0>(rel);
        std::string rId = std::get<2>(rel);

        std::vector<cell> cells = get_sheet_cells(sheet_id);
        worksheets.push_back(std::make_unique<worksheet>(cells, sheet_id, sheet_name, this));
    }
}

std::vector<cell> workbook::get_sheet_cells(std::uint32_t sheet_id) {
    std::vector<cell> cells;
    
    // Find the relation ID corresponding to this sheet_id
    std::string rId = "";
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == sheet_id) {
            rId = std::get<2>(rel);
            break;
        }
    }
    
    if (rId.empty()) return cells;

    auto xml_doc = my_archive->get_sheet_xml(rId);
    if (!xml_doc) return cells;

    tinyxml2::XMLElement* root = xml_doc->FirstChildElement("worksheet");
    if (!root) return cells;

    tinyxml2::XMLElement* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return cells;

    for (tinyxml2::XMLElement* cell_el = sheet_data->FirstChildElement("c"); 
         cell_el != nullptr; 
         cell_el = cell_el->NextSiblingElement("c")) {
        
        const char* cell_ref = cell_el->Attribute("r");
        if (!cell_ref) continue;

        // Parse "A1" -> row 1, col 1
        std::string ref_str = cell_ref;
        auto pos = ref_str.find_first_of("0123456789");
        if (pos == std::string::npos) continue;

        std::string col_str = ref_str.substr(0, pos);
        std::string row_str = ref_str.substr(pos);

        std::uint32_t row = std::stoul(row_str);
        std::uint32_t col = string_to_idx(col_str);

        std::uint32_t ss_idx = 0;
        tinyxml2::XMLElement* v_el = cell_el->FirstChildElement("v");
        if (v_el) {
            const char* type_attr = cell_el->Attribute("t");
            if (type_attr && std::string(type_attr) == "s") {
                // XLSX shared string index is 0-indexed in XML.
                // Since our workbook::shared_string is 1-indexed (index 0 is dummy),
                // we must add 1 to the index retrieved from XML.
                ss_idx = static_cast<std::uint32_t>(std::stoul(v_el->GetText())) + 1;
            } else {
                // If it's not a shared string, we treat it as a raw value 
                // but the requirement implies we mainly handle shared strings for text.
                // For simplicity in this conversion tool, we'll treat non-shared as index 0
                // or handle it via a different logic if needed.
                // Given the UML, ss_idx is the 3rd element.
                // Let's assume for now all text is shared.
                ss_idx = 0; 
            }
        }
        cells.emplace_back(row, col, ss_idx);
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
        std::string filename = ws->get_name() + ".csv";
        fs::path file_path = out_dir / filename;
        
        std::ofstream ofs(file_path);
        if (ofs.is_open()) {
            ofs << ws->to_csv();
            ofs.close();
        }
    }
}

} // namespace xlsx_reader
} // namespace my_xlsx
