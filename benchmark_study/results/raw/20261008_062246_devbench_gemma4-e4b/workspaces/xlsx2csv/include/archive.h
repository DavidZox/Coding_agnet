#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <string_view>
#include <tuple>
#include "tinyxml2.h"
#include "types.h" // Include types.h to get sheet_desc definition

// Forward declarations for types defined in types.h
// sheet_desc: std::tuple<std::string, std::uint32_t, std::string>
// cell: std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>

class Archive {
public:
    /**
     * @brief Constructor for Archive.
     * @param xlsx_filename Path to the XLSX file.
     */
    Archive(const std::string& xlsx_filename);

    /**
     * @brief Retrieves the relations for all sheets in the XLSX file.
     * @return A vector of sheet_desc tuples.
     */
    std::vector<sheet_desc> get_sheet_relations() const;

    /**
     * @brief Retrieves the XML document for a specific sheet.
     * @param sheet_relation_id The relation ID of the sheet.
     * @return A shared pointer to the tinyxml2::XMLDocument for the sheet.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_relation_id) const;

    /**
     * @brief Retrieves all shared strings from the XLSX file.
     * @return A vector of shared string content.
     */
    std::vector<std::string> get_shared_strings() const;

private:
    // Private member variables as per UML_class.md
    std::unordered_map<std::string, std::string_view> archive_content_;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content_;
    std::vector<void*> archive_files_;
};

#endif // ARCHIVE_H
