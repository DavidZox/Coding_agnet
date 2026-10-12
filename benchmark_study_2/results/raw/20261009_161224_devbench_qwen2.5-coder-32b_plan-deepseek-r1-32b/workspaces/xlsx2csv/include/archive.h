#ifndef ARCHIVE_H
#define ARCHIVE_H

#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <tinyxml2.h>

using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;

class archive {
public:
    archive(const std::string& filename);
    ~archive();

    std::vector<sheet_desc> get_sheet_relations();
    std::shared_ptr<tinyxml2::XMLDocument> get_sheet_xml(const std::string& sheet_path);
    std::vector<std::string> get_shared_strings();

private:
    std::unordered_map<std::string, std::string_view> archive_content;
    std::unordered_map<std::string, std::shared_ptr<tinyxml2::XMLDocument>> xml_content;
    std::vector<void*> archive_files;
};

#endif // ARCHIVE_H
