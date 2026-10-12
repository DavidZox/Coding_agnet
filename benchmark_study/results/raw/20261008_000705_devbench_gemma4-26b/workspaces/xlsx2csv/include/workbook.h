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
     * @brief Construct a new workbook object
     * @param filename Path to the XLSX file
     */
    workbook(const std::string& filename);

    /**
     * @brief Writes each worksheet to a separate CSV file in the specified directory
     * @param output_path The directory path where CSV files will be saved
     */
    void write_to_csv(std::string output_path);

    /**
     * @brief Retrieves a shared string by its index
     * @param idx The index of the shared string
     * @return std::string The shared string value
     */
    std::string get_shared_string(std::uint32_t idx) const;

private:
    /**
     * @brief Parses the XML of a specific sheet to extract cell information
     * @param sheet_id The ID of the sheet
     * @return std::vector<cell> A vector of cell tuples (row, col, shared_string_idx)
     */
    std::vector<cell> get_sheet_cells(std::uint32_t sheet_id);

    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
    std::shared_ptr<archive> my_archive;
    
    // Maps sheet_id to its list of cells
    std::unordered_map<std::uint32_t, std::vector<cell>> all_cells;
    
    // Maps shared string content to its index
    std::unordered_map<std::string, std::uint32_t> string_idx;
};

#endif // WORKBOOK_H
