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
     * @brief Gets the sheet relations from the archive.
     * @return A vector of sheet_desc.
     */
    std::vector<sheet_desc> get_sheet_relations();

    /**
     * @brief Gets the XML document for a specific sheet.
     * @param sheet_path The path to the sheet XML file within the archive.
     * @return A shared pointer to the XMLDocument.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);

    /**
     * @brief Gets the shared strings from the archive.
     * @return A vector of strings containing the shared strings.
     */
    std::vector<std::string> get_shared_strings();

private:
    std::unordered_map<std::string, std::string_view> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
};

#endif // ARCHIVE_H
