#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <cstdint>
#include <tuple> // Required for sheet_desc
#include <unordered_map> // Required for internal members if we were to fully implement, but keeping minimal based on prompt
#include <tinyxml2.h> // Include for XMLDocument type used in get_sheet_cells

// Forward declarations
class Archive;
class Worksheet;

// Type definitions from types.h (assuming they are available or defined here for completeness if needed, 
// but following the structure, we rely on types.h for the actual definition)
// sheet_desc: std::tuple<std::string, std::uint32_t, std::string>
// cell: std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>

class Workbook {
public:
    // Constructor: takes XLSX file path
    Workbook(const std::string& xlsx_filename);

    // Method to retrieve a shared string by index (1-based)
    std::string get_shared_string(std::uint32_t i) const;

    // Method to write all sheets to CSV files
    void write_to_csv(const std::string& output_path);

    // Method to retrieve cells for a specific sheet ID from its XML document
    std::vector<std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>> get_sheet_cells(std::uint32_t sheet_id, std::shared_ptr<tinyxml2::XMLDocument> sheet_xml) const;

private:
    // Members as per UML_class.md and sequence diagram
    std::shared_ptr<Archive> my_archive;
    std::vector<std::unique_ptr<Worksheet>> worksheets;
    std::vector<std::string> shared_string; // Stores shared strings (1-based indexing conceptually)
    std::vector<std::tuple<std::string, std::uint32_t, std::string>> sheet_relations;
    
    // Additional members mentioned in UML_class.md for completeness, though not strictly required for the interface definition requested
    std::unordered_map<std::uint32_t, std::vector<std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>>> all_cells;
    std::unordered_map<std::string, std::uint32_t> string_idx;
};

#endif // WORKBOOK_H
