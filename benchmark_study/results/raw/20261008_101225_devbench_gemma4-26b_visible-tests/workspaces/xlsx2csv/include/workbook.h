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
    void write_to_csv(const std::string& output_path);
    std::string get_shared_string(std::uint32_t index) const;

private:
    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<my_xlsx::xlsx_reader::sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
    std::shared_ptr<my_xlsx::xlsx_reader::archive> my_archive;
    std::vector<my_xlsx::xlsx_reader::cell> all_cells; // This is a placeholder for internal logic if needed
    std::unordered_map<std::string, std::uint32_t> string_idx;

    void get_sheet_cells(std::uint32_t sheet_id);
};

#endif // WORKBOOK_H
