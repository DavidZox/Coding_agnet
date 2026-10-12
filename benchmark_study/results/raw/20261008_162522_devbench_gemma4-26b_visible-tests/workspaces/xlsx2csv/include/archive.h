#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include "types.h"
#include "tinyxml2.h"

namespace my_xlsx {
namespace xlsx_reader {

class archive {
public:
    archive(const std::string& filename);
    std::vector<sheet_desc> get_sheet_relations();
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);
    std::vector<std::string> get_shared_strings();

private:
    std::unordered_map<std::string, std::string> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
    std::unordered_map<std::string, std::string> r_id_to_path;
};

} // namespace xlsx_reader
} // namespace my_xlsx

#endif // ARCHIVE_H
