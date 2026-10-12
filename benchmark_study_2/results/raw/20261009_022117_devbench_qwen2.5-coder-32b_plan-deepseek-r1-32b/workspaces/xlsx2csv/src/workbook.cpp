#include "workbook.h"
#include "archive.h"
#include "worksheet.h"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <sstream>

namespace xlsx2csv {

workbook::workbook(const std::string& filename)
    : my_archive(std::make_shared<archive>(filename)),
      shared_strings(my_archive->get_shared_strings()),
      sheet_relations(my_archive->get_sheet_relations()) {
    for (const auto& relation : sheet_relations) {
        std::string sheet_path = std::get<2>(relation);
        std::shared_ptr<tinyxml2::XMLDocument> sheet_xml = my_archive->get_sheet_xml(sheet_path);
        std::vector<cell> cells = get_sheet_cells(sheet_xml);
        std::string sheet_name = std::get<0>(relation);
        std::uint32_t sheet_id = std::get<1>(relation);
        create_worksheet(cells, sheet_id, sheet_name);
    }
}

std::string workbook::get_shared_string(std::uint32_t idx) const {
    if (idx > 0 && idx <= shared_strings.size()) {
        return shared_strings[idx - 1];
    }
    return "";
}

std::vector<cell> workbook::get_sheet_cells(const std::shared_ptr<tinyxml2::XMLDocument>& sheet_xml) {
    std::vector<cell> cells;
    tinyxml2::XMLElement* root = sheet_xml->RootElement();
    if (root) {
        for (tinyxml2::XMLElement* row = root->FirstChildElement("row"); row; row = row->NextSiblingElement("row")) {
            for (tinyxml2::XMLElement* cell = row->FirstChildElement("c"); cell; cell = cell->NextSiblingElement("c")) {
                std::string cell_ref = cell->Attribute("r");
                std::string cell_type = cell->Attribute("t");
                std::string cell_value = cell->FirstChildElement("v")->GetText();
                std::pair<std::uint32_t, std::uint32_t> row_col = utils::string_to_row_column(cell_ref);
                std::uint32_t row = row_col.first;
                std::uint32_t col = row_col.second;
                std::uint32_t shared_string_idx = 0;
                if (cell_type == "s") {
                    shared_string_idx = std::stoi(cell_value);
                }
                cells.emplace_back(row, col, shared_string_idx);
            }
        }
    }
    return cells;
}

void workbook::create_worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& sheet_name) {
    worksheets.emplace_back(std::make_unique<worksheet>(cells, sheet_id, sheet_name, this));
}

void workbook::write_to_csv(const std::string& output_path) {
    for (const auto& worksheet : worksheets) {
        std::string csv_data = worksheet->to_csv();
        std::string filename = output_path + "/" + worksheet->get_name() + ".csv";
        std::ofstream file(filename);
        if (file.is_open()) {
            file << csv_data;
            file.close();
        } else {
            std::cerr << "Error: Unable to open file " << filename << std::endl;
        }
    }
    std::cout << "Conversion successful. CSV files generated." << std::endl;
}

} // namespace xlsx2csv
