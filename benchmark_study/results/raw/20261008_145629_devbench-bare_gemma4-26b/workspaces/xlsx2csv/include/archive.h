#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map
#include <string_view>
#include "types.h"
#include "tinyxml2.h"

/**
 * @brief Archive class is used to read and write the xlsx file.
 */
class archive {
public:
    /**
     * @brief Constructor for Archive class.
     * @param filename Path to the xlsx file.
     */
    archive(const std::string& filename);

    /**
     * @brief Returns a list of sheet relations.
     * @return A vector of sheet_desc.
     */
    std::vector<sheet_desc> get_sheet_relations();

    /**
     * @brief Returns a sheet XML document.
     * @param sheet_path The path to the sheet XML within the archive.
     * @return A shared pointer to the XMLDocument.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);

    /**
     * @brief Returns the shared strings from the XLSX file.
     * @return A vector of strings containing shared strings.
     */
    std::vector<std::string> get_shared_strings();

private:
    std::unordered_map<std::string, std::string_view> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
};

#endif // ARCHIVE_H
