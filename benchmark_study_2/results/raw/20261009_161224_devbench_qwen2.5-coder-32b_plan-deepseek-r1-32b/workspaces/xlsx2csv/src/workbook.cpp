#include "workbook.h"
#include "archive.h"
#include "worksheet.h"
#include "utils.h"
#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <fstream>
#include <sstream>
#include <tinyxml2.h>
#include <iostream>

workbook::workbook(const std::string& filename)
    : my_archive(std::make_shared<archive>(filename)) {
    shared_strings = my_archive->get_shared_strings();
    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& relation : sheet_relations) {
        std::string sheet_path = "xl/worksheets/" + std::get<2>(relation) + ".xml";
        auto sheet_xml = my_archive->get_sheet_xml(sheet_path);
        std::vector<cell> cells = get_sheet_cells(sheet_xml);
        worksheets.emplace_back(std::make_unique<worksheet>(cells, std::get<1>(relation), std::get<0>(relation), this));
    }
}

std::vector<cell> workbook::get_sheet_cells(const std::shared_ptr<tinyxml2::XMLDocument>& sheet_xml) {
    std::vector<cell> cells;
    tinyxml2::XMLElement* root = sheet_xml->RootElement();
    for (tinyxml2::XMLElement* row = root->FirstChildElement("sheetData")->FirstChildElement("row"); row != nullptr; row = row->NextSiblingElement("row")) {
        for (tinyxml2::XMLElement* c = row->FirstChildElement("c"); c != nullptr; c = c->NextSiblingElement("c")) {
            const char* r = c->Attribute("r");
            const char* t = c->Attribute("t");
            const char* v = c->FirstChildElement("v")->GetText();
            auto [row_idx, col_idx] = utils::string_to_row_column(r);
            std::uint32_t shared_string_idx = 0;
            if (t && std::string(t) == "s") {
                shared_string_idx = std::stoi(v);
            }
            cells.emplace_back(row_idx, col_idx, shared_string_idx);
        }
    }
    return cells;
}

std::string workbook::get_shared_string(std::uint32_t idx) const {
    if (idx > 0 && idx <= shared_strings.size()) {
        return shared_strings[idx - 1];
    }
    return "";
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
