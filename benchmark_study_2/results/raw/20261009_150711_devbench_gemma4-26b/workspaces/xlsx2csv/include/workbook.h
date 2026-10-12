#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <cstdint>
#include "types.h"
#include "archive.h"
#include "worksheet.h"

class workbook {
public:
    /**
     * @brief Constructor for workbook.
     * Creates archive object and worksheet objects.
     * @param filename Path to the XLSX file.
     */
    workbook(const std::string& filename);

    /**
     * @brief Writes each worksheet to a separate CSV file.
     * @param output_path The directory or path where CSV files will be saved.
     */
    void write_to_csv(std::string output_path);

    /**
     * @brief Retrieves a shared string by its index.
     * @param idx The index of the shared string.
     * @return The shared string value.
     */
    std::string get_shared_string(std::uint32_t idx) const;

private:
    /**
     * @brief Parses the XML of a specific sheet to extract cell information.
     * @param sheet_id The ID of the sheet.
     * @return A vector of cells found in the sheet.
     */
    std::vector<cell> get_sheet_cells(std::uint32_t sheet_id);

    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
    std::shared_ptr<archive> my_archive;
    std::unordered_map<std::uint32_t, std::vector<cell>> all_cells;
    std::unordered_map<std::string, std::uint32_t> string_idx;
};

#endif // WORKBOOK_H
