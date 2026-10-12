#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <tinyxml2.h>

namespace xlsx2csv {

class archive {
public:
    archive(const std::string& filename);
    std::vector<sheet_desc> get_sheet_relations() const;
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path) const;
    std::vector<std::string> get_shared_strings() const;

private:
    std::unordered_map<std::string, std::string_view> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
};

} // namespace xlsx2csv

#endif // ARCHIVE_H
