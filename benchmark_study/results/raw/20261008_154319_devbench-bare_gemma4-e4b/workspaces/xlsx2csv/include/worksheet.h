#ifndef WORKSHEET_H
#define WORKSHEET_H

#include <string>
#include <vector>
#include <memory>
#include "types.h"
#include "workbook.h" // Forward declaration needed for pointer usage

/**
 * @brief Worksheet class is used to store the data of a sheet.
 */
class worksheet {
public:
    /**
     * @brief Constructor for Worksheet.
     * 
     * @param cells Vector of cells belonging to this sheet.
     * @param sheet_id The ID of the sheet.
     * @param sheet_name The name of the sheet.
     * @param workbook_ptr A pointer to the parent Workbook object.
     */
    worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& sheet_name, workbook* workbook_ptr);

    /**
     * @brief Retrieves the name of the worksheet.
     * 
     * @return std::string The name of the sheet.
     */
    std::string get_name() const;

    /**
     * @brief Converts the sheet data into a CSV formatted string.
     * 
     * @return std::string A string containing the CSV data for this sheet.
     */
    std::string to_csv() const;

private:
    const std::string _name;
    const std::uint32_t _sheet_id;
    workbook* _workbook; // Pointer to the parent workbook
    const std::vector<cell> _cells;
};

#endif // WORKSHEET_H
