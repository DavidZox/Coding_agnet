#ifndef WORKSHEET_H
#define WORKSHEET_H

#include <string>
#include <vector>
#include <cstdint>
#include "types.h"

// Forward declaration of workbook to avoid circular dependency
class workbook;

/**
 * @brief Worksheet class is used to store the data of a sheet.
 */
class worksheet {
public:
    /**
     * @brief Constructor for Worksheet class.
     * @param cells A vector of sheet cells.
     * @param sheet_id The ID of the sheet.
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
    
    std::uint32_t row_num;
    std::uint32_t column_num;
    std::vector<std::vector<std::uint32_t>> row_info;
};

#endif // WORKSHEET_H
