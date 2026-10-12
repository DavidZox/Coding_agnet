#include "workbook.h"
#include <fstream>
#include <sstream>
#include <algorithm>

namespace xlsx2csv {

workbook::workbook(const std::string& filename)
    : my_archive(std::make_shared<archive>(filename)) {
    shared_strings = my_archive->get_shared_strings();
    sheet_relations = my_archive->get_sheet_relations();

    for (const auto& relation : sheet_relations) {
        std::uint32_t sheet_id = std::get<1>(relation);
        std::vector<cell> cells = get_sheet_cells(sheet_id);
        all_cells[sheet_id] = cells;
        std::string sheet_name = std::get<0>(relation);
        worksheets.emplace_back(std::make_unique<worksheet>(cells, sheet_id, sheet_name, this));
    }
}

void workbook::write_to_csv(const std::string& output_path) {
    for (const auto& worksheet_ptr : worksheets) {
        std::string sheet_name = worksheet_ptr->get_name();
        std::string csv_data = worksheet_ptr->to_csv();
        std::string file_path = output_path + "/" + sheet_name + ".csv";

        std::ofstream csv_file(file_path);
        if (csv_file.is_open()) {
            csv_file << csv_data;
            csv_file.close();
        } else {
            throw std::runtime_error("Unable to open file: " + file_path);
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

std::vector<cell> workbook::get_sheet_cells(std::uint32_t sheet_id) {
    std::vector<cell> cells;
    for (const auto& relation : sheet_relations) {
        if (std::get<1>(relation) == sheet_id) {
            std::string sheet_path = std::get<2>(relation);
            auto sheet_xml = my_archive->get_sheet_xml(sheet_path);
            if (sheet_xml) {
                auto* sheet_data = sheet_xml->FirstChildElement("worksheet");
                if (sheet_data) {
                    auto* sheet_data_child = sheet_data->FirstChildElement("sheetData");
                    if (sheet_data_child) {
                        for (auto* row = sheet_data_child->FirstChildElement("row"); row; row = row->NextSiblingElement("row")) {
                            for (auto* cell = row->FirstChildElement("c"); cell; cell = cell->NextSiblingElement("c")) {
                                const char* r = cell->Attribute("r");
                                const char* t = cell->Attribute("t");
                                if (r) {
                                    auto [row_num, col_num] = string_to_row_column(r);
                                    std::uint32_t shared_string_idx = 0;
                                    if (t && std::string(t) == "s") {
                                        const char* v = cell->FirstChildElement("v")->GetText();
                                        if (v) {
                                            shared_string_idx = static_cast<std::uint32_t>(std::stoi(v));
                                        }
                                    }
                                    cells.emplace_back(row_num, col_num, shared_string_idx);
                                }
                            }
                        }
                    }
                }
            }
            break;
        }
    }
    return cells;
}

} // namespace xlsx2csv
