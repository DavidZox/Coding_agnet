#include "archive.h"
#include "miniz.h"
#include "tinyxml2.h"
#include "types.h"
#include <vector>
#include <string>
#include <string_view>
#include <unordered_map>
#include <memory>
#include <tuple>
#include <cstring>

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    std::memset(&zip_archive, 0, sizeof(zip_archive));

    if (mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0) != MZ_OK) {
        return;
    }

    mz_uint num_files = mz_zip_reader_get_num_files(&zip_archive);
    for (mz_uint i = 0; i < num_files; ++i) {
        mz_zip_archive_file_stat file_stat;
        if (mz_zip_reader_file_stat(&zip_archive, i, &file_stat) != MZ_OK) {
            continue;
        }

        std::string file_path = file_stat.m_filename;
        
        // Allocate memory to hold the uncompressed file content
        void* buffer = malloc(file_stat.m_uncomp_size);
        if (!buffer) continue;

        if (mz_zip_read_archive_data(&zip_archive, i, buffer, file_stat.m_uncomp_size) != MZ_OK) {
            free(buffer);
            continue;
        }

        // Store the pointer in archive_files to manage lifetime
        archive_files.push_back(buffer);
        
        // Map the file path to the string_view pointing to the buffer
        archive_content[file_path] = std::string_view(static_cast<const char*>(buffer), file_stat.m_uncomp_size);
    }

    mz_zip_reader_end(&zip_archive);
}

archive::~archive() {
    for (void* ptr : archive_files) {
        free(ptr);
    }
}

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    std::string rel_path = "xl/_rels/workbook.xml.rels";
    
    auto it = archive_content.find(rel_path);
    if (it == archive_content.end()) return relations;

    tinyxml2::XMLDocument doc;
    if (doc.Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return relations;
    }

    tinyxml2::XMLElement* root = doc.FirstChildElement("Relationships");
    if (!root) return relations;

    for (tinyxml2::XMLElement* rel = root->FirstChildElement("Relationship"); rel != nullptr; rel = rel->NextSiblingElement("Relationship")) {
        const char* target = rel->Attribute("Target");
        const char* id = rel->Attribute("Id");
        
        if (target && id) {
            // In XLSX, sheet relations are often relative to xl/ folder or absolute.
            // The workbook.xml.rels is in xl/_rels/, so Target "sheets/sheet1.xml" 
            // actually means "xl/sheets/sheet1.xml".
            // However, the standard says Target is relative to the directory of the rels file.
            // xl/_rels/workbook.xml.rels -> Target "sheets/sheet1.xml" -> xl/sheets/sheet1.xml
            
            std::string full_target = "xl/" + std::string(target);
            // Handle cases where target might already start with xl/ if it was absolute-ish
            if (full_target.find("xl/xl/") == 0) {
                full_target = full_target.substr(3);
            }

            // We need a way to get the sheet name. Usually, sheet name is in workbook.xml.
            // But the UML says sheet_desc is (name, id, rId). 
            // Since we don't have the name here, we'll use the target as a placeholder 
            // or we'll have to parse workbook.xml later. 
            // Looking at the sequence, Workbook handles the mapping.
            // Let's just store the rId and the path.
            // To satisfy the tuple<string, uint32, string>, we'll use the target as name.
            relations.emplace_back(target, 0, id); 
        }
    }
    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) {
    // sheet_path is expected to be the target from rels, e.g., "sheets/sheet1.xml"
    // which corresponds to "xl/sheets/sheet1.xml"
    std::string full_path = "xl/" + sheet_path;
    
    if (xml_content.count(full_path)) {
        return xml_content[full_path];
    }

    auto it = archive_content.find(full_path);
    if (it == archive_content.end()) return nullptr;

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return nullptr;
    }

    xml_content[full_path] = doc;
    return doc;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    std::string path = "xl/sharedStrings.xml";

    auto it = archive_content.find(path);
    if (it == archive_content.end()) return strings;

    tinyxml2::XMLDocument doc;
    if (doc.Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return strings;
    }

    tinyxml2::XMLElement* root = doc.FirstChildElement("sst");
    if (!root) return strings;

    for (tinyxml2::XMLElement* si = root->FirstChildElement("si"); si != nullptr; si = si->NextSiblingElement("si")) {
        tinyxml2::XMLElement* t = si->FirstChildElement("t");
        if (t && t->GetText()) {
            strings.push_back(t->GetText());
        } else if (t) {
            strings.push_back("");
        }
    }

    return strings;
}
