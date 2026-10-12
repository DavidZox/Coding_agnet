#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include "types.h"
#include "archive.h"
#include "worksheet.h"

/**
 * @brief Workbook class is the main class of the software.
 */
class workbook {
public:
    /**
     * @brief Constructor for Workbook.
     * 
     * @param xlsx_filename The path of the XLSX file.
     */
    workbook(const std::string& xlsx_filename);

    /**
     * @brief Writes the workbook data to CSV files based on sheet names.
     * 
     * @param output_path The base path where CSV files should be saved.
     */
    void write_to_csv(const std::string& output_path);

    /**
     * @brief Retrieves a shared string by its 1-based index.
     * 
     * @param index The 1-based index of the shared string.
     * @return std::string The shared string content.
     */
    std::string get_shared_string(std::uint32_t index) const;

private:
    // Members as described in UML_class.md and architecture_design.md
    std::shared_ptr<archive> my_archive;
    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_strings; // 1-based indexing conceptually
    std::unordered_map<std::uint32_t, std::vector<cell>> all_cells; // Map SheetID -> vector<cell>
    std::unordered_map<std::string, std::uint32_t> string_to_idx; // Not explicitly required by UML but useful for implementation

    // Private helper methods
    std::vector<cell> get_sheet_cells(std::uint32_t sheet_id) const;
};

#endif // WORKBOOK_H
