#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <cstdint>
#include "archive.h"
#include "worksheet.h"
#include "types.h"

/**
 * @brief Workbook class is the main class of the software.
 */
class workbook {
public:
    /**
     * @brief Constructor for Workbook class.
     * @param filename Path to the xlsx file.
     */
    workbook(const std::string& filename);

    /**
     * @brief Writes the workbook data to CSV files.
     * @param output_path The directory path where CSV files will be saved.
     */
    void write_to_csv(std::string output_path);

    /**
     * @brief Returns a shared string by its index.
     * @param i The index in shared_string.
     * @return The shared string value.
     */
    std::string get_shared_string(std::uint32_t i) const;

private:
    /**
     * @brief Retrieves cells for a specific sheet.
     * @param i The sheet id.
     * @return A vector of cells for the sheet.
     */
    std::vector<cell> get_sheet_cells(std::uint32_t i);

    std::shared_ptr<archive> my_archive;
    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
    std::unordered_map<std::uint32_t, std::vector<cell>> all_cells;
    std::unordered_map<std::string, std::uint32_t> string_idx;
};

#endif // WORKBOOK_H
