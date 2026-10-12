#include "workbook.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <filesystem>

namespace fs = std::filesystem;

workbook::workbook(const std::string& filename) {
    my_archive = std::make_shared<archive>(filename);
    
    // Shared strings are started from index 1, so we add a dummy at index 0
    shared_string.push_back(""); 
    std::vector<std::string> ss_list = my_archive->get_shared_strings();
    for (const auto& s : ss_list) {
        shared_string.push_back(s);
    }

    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& relation : sheet_relations) {
        // relation: tuple<name, id, rId>
        std::string name = std::get<0>(relation);
        std::uint32_t id = std::get<1>(relation);
        std::string rId = std::get<2>(relation);

        std::vector<cell> cells = get_sheet_cells(id);
        worksheets.push_back(std::make_unique<worksheet>(cells, id, name, this));
    }
}

std::string workbook::get_shared_string(std::uint32_t i) const {
    if (i > 0 && i < shared_string.size()) {
        return shared_string[i];
    }
    return "";
}

std::vector<cell> workbook::get_sheet_cells(std::uint32_t i) {
    // Find the relation ID for this sheet ID
    std::string rId = "";
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == i) {
            rId = std::get<2>(rel);
            break;
        }
    }

    std::vector<cell> cells;
    if (rId.empty()) return cells;

    auto xml_doc = my_archive->get_sheet_xml(rId);
    if (!xml_doc) return cells;

    auto* root = xml_doc->FirstChildElement("worksheet");
    if (!root) return cells;

    auto* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return cells;

    for (auto* row_node = sheet_data->FirstChildElement("row"); row_node != nullptr; row_node = row_node->NextSiblingElement("row")) {
        for (auto* cell_node = row_node->FirstChildElement("c"); cell_node != nullptr; cell_node = cell_node->NextSiblingElement("c")) {
            std::string ref = cell_node->Attribute("r") ? cell_node->Attribute("r") : "";
            if (ref.empty()) continue;

            auto [row_idx, col_idx] = string_to_row_column(ref);
            
            std::uint32_t ss_idx = 0;
            auto* v = cell_node->FirstChildElement("v");
            if (v) {
                ss_idx = static_cast<std::uint32_t>(v->GetText() ? std::stoul(v->GetText()) : 0);
            }

            // cell: tuple<row, col, ss_idx>
            cells.push_back(std::make_tuple(row_idx, col_idx, ss_idx));
        }
    }

    return cells;
}

void workbook::write_to_csv(std::string output_path) {
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
