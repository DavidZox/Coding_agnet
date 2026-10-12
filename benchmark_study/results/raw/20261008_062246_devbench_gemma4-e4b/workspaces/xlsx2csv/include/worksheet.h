#ifndef WORKSHEET_H
#define WORKSHEET_H

#include <string>
#include <vector>
#include <cstdint>
#include <memory>
#include <tuple>

// Forward declarations
class Workbook;

// Type definitions from types.h (assuming they are available or defined here for completeness)
// In a real scenario, these would be included from types.h
using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

class Worksheet {
public:
    // Constructor as per requirement
    Worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& sheet_name, Workbook* workbook_ptr);

    // Public methods
    std::string get_name() const;
    std::string to_csv() const;

private:
    // Private members as per requirement
    const std::string _name;
    const std::uint32_t _sheet_id;
    Workbook* _workbook; // Pointer to Workbook - CHANGED FROM const void*
    const std::vector<cell> _cells;

    // Members mentioned in UML/Design, though their usage might be internal/derived
    // Keeping them as per UML_class.md structure, even if not strictly used in the simple interface definition
    std::uint32_t row_num;
    std::uint32_t column_num;
};

#endif // WORKSHEET_H
