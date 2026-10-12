#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <string_view>
#include "types.h"
#include "tinyxml2.h"
#include "miniz.h"

class archive {
public:
    /**
     * @brief Construct a new archive object
     * @param filename Path to the XLSX file
     */
    archive(const std::string& filename);

    /**
     * @brief Destructor for archive object
     */
    ~archive();

    /**
     * @brief Get the sheet relations from the XLSX file
     * @return std::vector<sheet_desc> A list of sheet relations
     */
    std::vector<sheet_desc> get_sheet_relations();

    /**
     * @brief Get the XML document for a specific sheet
     * @param sheet_path The path to the sheet XML within the archive
     * @return std::shared_ptr<tinyxml2::XMLDocument> Shared pointer to the XML document
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);

    /**
     * @brief Get the shared strings from the XLSX file
     * @return std::vector<std::string> A list of shared strings
     */
    std::vector<std::string> get_shared_strings();

private:
    std::unordered_map<std::string, std::string_view> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
};

#endif // ARCHIVE_H
