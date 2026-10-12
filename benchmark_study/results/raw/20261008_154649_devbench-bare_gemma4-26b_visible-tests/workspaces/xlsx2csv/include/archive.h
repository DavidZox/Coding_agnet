#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <string_view>
#include "types.h"
#include "tinyxml2.h"

namespace my_xlsx::xlsx_reader {

/**
 * @brief Archive class is used to read and write the xlsx file.
 * It handles the extraction of XML files from the zip container and provides
 * access to sheet relations and shared strings.
 */
class archive {
public:
    /**
     * @brief Constructor for archive.
     * @param filename Path to the xlsx file.
     */
    explicit archive(const std::string& filename);

    /**
     * @brief Returns a list of sheet relations.
     * @return A vector of sheet_desc.
     */
    std::vector<sheet_desc> get_sheet_relations();

    /**
     * @brief Returns a sheet XML document.
     * @param sheet_path The path to the sheet XML within the archive (e.g., "xl/worksheets/sheet1.xml").
     * @return A shared pointer to the tinyxml2::XMLDocument.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);

    /**
     * @brief Returns the shared strings from the XLSX file.
     * @return A vector of strings containing the shared strings.
     */
    std::vector<std::string> get_shared_strings();

private:
    // archive_content stores the raw content of files in the archive.
    std::unordered_map<std::string, std::string_view> archive_content;
    
    // xml_content stores parsed XML documents.
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    
    // archive_files stores pointers to the unzipped data (implementation detail for miniz/zip).
    std::vector<void*> archive_files;
};

} // namespace my_xlsx::xlsx_reader

#endif // ARCHIVE_H
