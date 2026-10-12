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

namespace my_xlsx::xlsx_reader {

/**
 * @brief Workbook class is the main class of the software.
 * It manages the archive, shared strings, sheet relations, and worksheets.
 */
class workbook {
public:
    /**
     * @brief Constructor for workbook.
     * @param filename Path to the xlsx file.
     */
    explicit workbook(const std::string& filename);

    /**
     * @brief Writes each worksheet to a separate CSV file in the specified directory.
     * @param output_path The directory path where CSV files will be saved.
     */
    void write_to_csv(const std::string& output_path);

    /**
     * @brief Returns a shared string by its index.
     * @param i The index of the shared string.
     * @return The shared string value.
     */
    std::string get_shared_string(std::uint32_t i) const;

private:
    /**
     * @brief Parses the sheet XML to extract cell information.
     * @param sheet_id The ID of the sheet.
     * @return A vector of cell tuples (row, column, shared_string_idx).
     */
    std::vector<cell> get_sheet_cells(std::uint32_t sheet_id);

    std::shared_ptr<archive> my_archive;
    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
    
    // Maps cell coordinates or other identifiers if needed, 
    // though the UML suggests all_cells might be used for internal processing.
    std::unordered_map<std::uint32_t, std::vector<cell>> all_cells;
    std::unordered_map<std::string, std::uint32_t> string_idx;
};

} // namespace my_xlsx::xlsx_reader

#endif // WORKBOOK_H
