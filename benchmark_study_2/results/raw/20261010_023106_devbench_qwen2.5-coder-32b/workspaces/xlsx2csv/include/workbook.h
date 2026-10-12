#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <tuple>
#include "archive.h"
#include "worksheet.h"

using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

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

    std::vector<cell> get_sheet_cells(std::uint32_t sheet_id);
};

#endif // WORKBOOK_H
