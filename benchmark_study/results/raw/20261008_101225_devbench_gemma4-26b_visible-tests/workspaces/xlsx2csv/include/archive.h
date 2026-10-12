#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <string_view>
#include <tuple>
#include <cstdint>
#include "types.h"
#include "tinyxml2.h"
#include "miniz.h"

namespace my_xlsx::xlsx_reader {

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
    std::vector<my_xlsx::xlsx_reader::sheet_desc> get_sheet_relations();

    /**
     * @brief Retrieves the XML document for a specific sheet.
     * @param sheet_path The path to the sheet XML within the archive.
     * @return A shared pointer to the parsed XMLDocument.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);

    /**
     * @brief Retrieves the shared strings from the XLSX file.
     * @return A vector of strings containing the shared strings.
     */
    std::vector<std::string> get_shared_strings();

private:
    // Maps file paths within the zip to their raw content string_view
    std::unordered_map<std::string, std::string_view> archive_content;
    
    // Caches parsed XML documents
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    
    // The zip archive structure
    mz_zip_archive zip_archive;

    // Internal helper to ensure a file is loaded into archive_content
    bool load_file_to_content(const std::string& filename, const std::string& file_in_zip);
};

} // namespace my_xlsx::xlsx_reader

#endif // ARCHIVE_H
