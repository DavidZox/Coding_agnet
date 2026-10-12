#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <tinyxml2.h>

#include "types.h"

class archive {
public:
    archive(const std::string&);
    std::vector<sheet_desc> get_sheet_relations() const;
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string&) const;
    std::vector<std::string> get_shared_strings() const;

private:
    std::unordered_map<std::string, std::string_view> archive_content;
    mutable std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
};

#endif // ARCHIVE_H
