#include "workbook.h"
#include "archive.h"
#include "worksheet.h"
#include "utils.h"
#include <tinyxml2.h>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <iostream>

namespace {

std::vector<cell> parse_sheet_xml(const std::shared_ptr<tinyxml2::XMLDocument>& sheet_xml, const std::vector<std::string>& shared_strings) {
    std::vector<cell> cells;
    tinyxml2::XMLElement* root = sheet_xml->RootElement();
    if (!root) return cells;

    for (tinyxml2::XMLElement* row = root->FirstChildElement("sheetData")->FirstChildElement("row"); row; row = row->NextSiblingElement("row")) {
        for (tinyxml2::XMLElement* cell = row->FirstChildElement("c"); cell; cell = cell->NextSiblingElement("c")) {
            std::string cell_ref = cell->Attribute("r");
            std::pair<std::uint32_t, std::uint32_t> row_col = utils::string_to_row_column(cell_ref);
            std::uint32_t row = row_col.first;
            std::uint32_t col = row_col.second;

            std::uint32_t shared_string_idx = 0;
            if (cell->Attribute("t") && std::string(cell->Attribute("t")) == "s") {
                shared_string_idx = std::stoul(cell->FirstChildElement("v")->GetText());
            }
            cells.emplace_back(row, col, shared_string_idx);
        }
    }
    return cells;
}

} // namespace

workbook::workbook(const std::string& filename)
    : my_archive(std::make_shared<archive>(filename)), shared_strings(my_archive->get_shared_strings()), sheet_relations(my_archive->get_sheet_relations()) {
    for (const auto& relation : sheet_relations) {
        std::string sheet_path = std::get<2>(relation);
        std::shared_ptr<tinyxml2::XMLDocument> sheet_xml = my_archive->get_sheet_xml(sheet_path);
        std::vector<cell> cells = parse_sheet_xml(sheet_xml, shared_strings);
        std::string sheet_name = std::get<0>(relation);
        std::uint32_t sheet_id = std::get<1>(relation);
        worksheets.emplace_back(std::make_unique<xlsx2csv::worksheet>(cells, sheet_id, sheet_name, this));
    }
}

void workbook::write_to_csv(const std::string& output_path) {
    for (const auto& worksheet : worksheets) {
        std::string csv_data = worksheet->to_csv();
        std::string filename = output_path + "/" + worksheet->get_name() + ".csv";
        std::ofstream file(filename);
        if (file.is_open()) {
            file << csv_data;
            file.close();
        }
    }
    std::cout << "Conversion successful. CSV files generated." << std::endl;
}

std::string workbook::get_shared_string(std::uint32_t idx) const {
    if (idx > 0 && idx <= shared_strings.size()) {
        return shared_strings[idx - 1];
    }
    return "";
}
