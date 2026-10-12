#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <string_view>
#include "types.h"
#include "tinyxml2.h"

// Forward declarations
class workbook;

/**
 * @brief Archive class is used to read and write the xlsx file.
 */
class archive {
public:
    /**
     * @brief Constructor for Archive.
     * 
     * @param xlsx_filename The path of the xlsx file.
     */
    archive(const std::string& xlsx_filename);

    /**
     * @brief Retrieves a list of sheet relations.
     * 
     * @return std::vector<sheet_desc> A list of sheet relations.
     */
    std::vector<sheet_desc> get_sheet_relations() const;

    /**
     * @brief Retrieves the XML document for a specific sheet.
     * 
     * @param sheet_relation_id The relation ID of the sheet.
     * @return std::shared_ptr<tinyxml2::XMLDocument> The XML document for the sheet.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_relation_id) const;

    /**
     * @brief Retrieves all shared strings from the XLSX file.
     * 
     * @return std::vector<std::string> A vector containing all shared strings.
     */
    std::vector<std::string> get_shared_strings() const;

private:
    // Internal members as described in UML_class.md
    std::unordered_map<std::string, std::string_view> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files; // Placeholder for zip file entries
};

#endif // ARCHIVE_H
