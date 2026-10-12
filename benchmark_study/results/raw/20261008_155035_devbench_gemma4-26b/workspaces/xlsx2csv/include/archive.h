#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <string_view>
#include <tuple>
#include "types.h"
#include "tinyxml2.h"

class archive {
public:
    /**
     * @brief Constructor for the archive class.
     * @param filename The path to the XLSX file.
     */
    archive(const std::string& filename);

    /**
     * @brief Destructor for the archive class.
     */
    ~archive();

    /**
     * @brief Retrieves the sheet relations from the XLSX file.
     * @return A vector of sheet_desc tuples.
     */
    std::vector<sheet_desc> get_sheet_relations();

    /**
     * @brief Retrieves the XML content of a specific sheet.
     * @param sheet_path The internal path to the sheet XML within the archive.
     * @return A shared pointer to a tinyxml2::XMLDocument.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);

    /**
     * @brief Retrieves the shared strings from the XLSX file.
     * @return A vector of strings containing the shared strings.
     */
    std::vector<std::string> get_shared_strings();

private:
    std::string filename_;
    
    // Cache for uncompressed file contents
    std::unordered_map<std::string, std::string> archive_content;
    
    // Cache for parsed XML documents
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;

    // Internal helper to get uncompressed data from the zip archive
    std::string get_uncompressed_file(const std::string& internal_path);
};

#endif // ARCHIVE_H
