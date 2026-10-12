#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <string_view>
#include <tuple>
#include <tinyxml2.h>

// Forward declarations for types defined in types.h (assuming types.h exists and defines them)
// Since we are only implementing archive.h now, we rely on the structure defined in UML_class.md
// sheet_desc: std::tuple<std::string, std::uint32_t, std::string>
// cell: std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>

// Define types locally or assume they are available via types.h inclusion later.
// For this specific file, we must assume necessary types are available or define placeholders if required for compilation context.
// Based on the prompt, types.h should contain these definitions. We include it here for completeness if it were available.
#include "types.h" 

class Archive {
public:
    /**
     * @brief Constructor for Archive.
     * @param xlsx_filename Path to the XLSX file.
     */
    Archive(const std::string& xlsx_filename);

    /**
     * @brief Retrieves a list of sheet relations from the XLSX file.
     * @return std::vector<sheet_desc> A vector containing sheet name, ID, and relation ID.
     */
    std::vector<sheet_desc> get_sheet_relations() const;

    /**
     * @brief Retrieves the XML document for a specific sheet.
     * @param sheet_path A path/identifier for the sheet XML.
     * @return std::shared_ptr<tinyxml2::XMLDocument> A shared pointer to the sheet's XML document.
     */
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path) const;

    /**
     * @brief Retrieves all shared strings from the XLSX file.
     * @return std::vector<std::string> A vector containing all shared strings.
     */
    std::vector<std::string> get_shared_strings() const;

private:
    // Private members as defined in UML_class.md
    std::unordered_map<std::string, std::string_view> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
};

#endif // ARCHIVE_H
