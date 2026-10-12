#ifndef WORKSHEET_H
#define WORKSHEET_H

#include <string>
#include <vector>
#include <cstdint>
#include <memory>

// Forward declarations
class Workbook;

// Type definitions from types.h (assuming they are available or defined here for simplicity in header)
// In a real scenario, these would be included from types.h
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

/**
 * @brief Worksheet class is used to store the data of a sheet.
 */
class Worksheet {
public:
    /**
     * @brief Constructor for Worksheet.
     * 
     * @param cells Vector of cells belonging to this sheet.
     * @param sheet_id Unique ID of the sheet.
     * @param name Name of the sheet.
     * @param workbook Pointer to the parent Workbook object.
     */
    Worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, Workbook* workbook);

    /**
     * @brief Gets the name of the worksheet.
     * 
     * @return std::string The sheet name.
     */
    std::string get_name() const;

    /**
     * @brief Converts the sheet data into a CSV formatted string.
     * 
     * @return std::string The CSV data string.
     */
    std::string to_csv() const;

private:
    const std::string _name;
    const std::uint32_t _sheet_id;
    Workbook* _workbook; // Pointer to the parent workbook
    const std::vector<cell> _cells;
    
    // Members mentioned in UML class diagram, though not strictly necessary for the interface defined in PRD/UML
    // For completeness based on UML, we keep them private members.
    std::uint32_t row_num;
    std::uint32_t column_num;
    std::vector<std::vector<std::uint32_t>> row_info;
};

#endif // WORKSHEET_H
