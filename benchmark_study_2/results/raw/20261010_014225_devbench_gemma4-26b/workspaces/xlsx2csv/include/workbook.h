#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include "types.h"
#include "archive.h"
#include "worksheet.h"

class workbook {
public:
    workbook(const std::string& filename);
    void write_to_csv(std::string output_path);
    std::string get_shared_string(std::uint32_t i) const;

private:
    void get_sheet_cells(std::uint32_t i);

    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
    std::shared_ptr<archive> my_archive;
    std::unordered_map<std::uint32_t, std::vector<cell>> all_cells;
    std::unordered_map<std::string, std::uint32_t> string_idx;
};

#endif // WORKBOOK_H
