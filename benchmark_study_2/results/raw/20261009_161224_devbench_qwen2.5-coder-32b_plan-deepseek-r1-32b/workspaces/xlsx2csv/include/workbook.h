#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <tinyxml2.h>
#include "archive.h"
#include "worksheet.h"
#include "utils.h"

class workbook {
public:
    workbook(const std::string& filename);
    void write_to_csv(const std::string& output_path);
    std::string get_shared_string(std::uint32_t idx) const;

private:
    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_strings;
    std::shared_ptr<archive> my_archive;
    std::unordered_map<std::uint32_t, std::vector<cell>> all_cells;
    std::unordered_map<std::string, std::uint32_t> string_idx;

    std::vector<cell> get_sheet_cells(const std::shared_ptr<tinyxml2::XMLDocument>& sheet_xml);
};

#endif // WORKBOOK_H
