#ifndef WORKSHEET_H
#define WORKSHEET_H

#include <string>
#include <vector>
#include <cstdint>
#include "types.h"

namespace my_xlsx {
namespace xlsx_reader {

// Forward declaration of workbook class
class workbook;

class worksheet {
public:
    /**
     * @brief Constructor for worksheet.
     * @param cells A vector of cell tuples (row, col, shared_string_idx).
     * @param sheet_id The unique ID of the sheet.
     * @param name The name of the sheet.
     * @param wb A pointer to the workbook instance.
     */
    worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, const workbook* wb);

    /**
     * @brief Returns the name of the worksheet.
     * @return The sheet name as a string.
     */
    std::string get_name() const;

    /**
     * @brief Converts the worksheet data into a CSV formatted string.
     * @return A string containing the CSV data.
     */
    std::string to_csv() const;

private:
    const std::string _name;
    const std::uint32_t _sheet_id;
    const workbook* _workbook;
    const std::vector<cell> _cells;

    // Internal variables to track dimensions and structure for CSV generation
    std::uint32_t row_num;
    std::uint32_t column_num;
    // row_info stores the column indices present in each row to handle sparse data
    // row_info[row_index] = {col_index1, col_index2, ...}
    std::vector<std::vector<std::uint32_t>> row_info;
};

} // namespace xlsx_reader
} // namespace my_xlsx

#endif // WORKSHEET_H
