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

namespace my_xlsx {
namespace xlsx_reader {

class workbook {
public:
    /**
     * @brief Constructor for workbook.
     * @param filename Path to the XLSX file.
     */
    workbook(const std::string& filename);

    /**
     * @brief Writes each worksheet to a separate CSV file.
     * @param output_path The directory or path where CSV files will be saved.
     */
    void write_to_csv(std::string output_path);

    /**
     * @brief Gets a shared string by its index.
     * @param idx The index of the shared string.
     * @return The shared string value.
     */
    std::string get_shared_string(std::uint32_t idx) const;

private:
    /**
     * @brief Parses the XML of a sheet to extract cell information.
     * @param sheet_id The ID of the sheet.
     * @return A vector of cell tuples.
     */
    std::vector<cell> get_sheet_cells(std::uint32_t sheet_id);

    std::shared_ptr<archive> my_archive;
    std::vector<std::unique_ptr<worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
};

} // namespace xlsx_reader
} // namespace my_xlsx

#endif // WORKBOOK_H
