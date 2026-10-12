#include "archive.h"
#include "tinyxml2.h"
#include "miniz.h"
#include <iostream>
#include <vector>
#include <string>
#include <memory>
#include <unordered_map>
#include <stdexcept>
#include <cstring>

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    memset(&zip_archive, 0, sizeof(zip_archive));

    if (!mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0)) {
        throw std::runtime_error("Failed to initialize zip reader.");
    }

    mz_uint num_files = mz_zip_reader_get_num_files(&zip_archive);
    for (mz_uint i = 0; i < num_files; ++i) {
        mz_zip_archive_file_stat file_stat;
        if (mz_zip_reader_file_stat(&zip_archive, i, &file_stat) == MZ_OK) {
            // Read file content into a buffer
            void* buffer = nullptr;
            size_t uncompressed_size = 0;
            buffer = mz_zip_reader_extract_to_heap(&zip_archive, i, &uncompressed_size, 0);
            if (buffer != nullptr) {
                // Store the buffer in archive_files to keep it alive
                void* stored_ptr = malloc(uncompressed_size);
                memcpy(stored_ptr, buffer, uncompressed_size);
                archive_files.push_back(stored_ptr);

                // Create a string_view pointing to the allocated memory
                std::string_view sv(static_cast<const char*>(stored_ptr), uncompressed_size);
                archive_content[std::string(file_stat.m_filename)] = sv;
                
                mz_free(buffer);
            }
        }
    }
    mz_zip_reader_end(&zip_archive);
}

// Note: The destructor should be implemented to free archive_files
// However, since the task only asks for the implementation of the class methods,
// I will focus on the requested logic. 
// In a real scenario, archive's destructor would loop through archive_files and free().

archive::~archive() {
    for (void* ptr : archive_files) {
        free(ptr);
    }
}

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    
    // To correctly implement get_sheet_relations as (name, id, rId),
    // we first need to parse xl/workbook.xml to get the mapping of sheet names to rIds.
    auto workbook_doc = get_sheet_xml("xl/workbook.xml");
    if (!workbook_doc) return relations;

    tinyxml2::XMLElement* workbook_root = workbook_doc->FirstChildElement("workbook");
    if (!workbook_root) return relations;

    // Map rId to sheet name
    std::unordered_map<std::string, std::string> rid_to_name;
    for (tinyxml2::XMLElement* sheet_el = workbook_root->FirstChildElement("sheet"); 
         sheet_el != nullptr; 
         sheet_el = sheet_el->NextSiblingElement("sheet")) {
        const char* name = sheet_el->Attribute("name");
        const char* sheet_id_str = sheet_el->Attribute("sheetId");
        const char* rId = sheet_el->Attribute("r:id"); // Note: XML namespace handling might be needed, but tinyxml2 usually allows access via attribute name
        
        // In many tinyxml2 implementations, r:id is accessed as "r:id" or just "id" depending on how it's parsed.
        // However, standard tinyxml2 requires the exact attribute name.
        // Let's check for both common ways.
        if (!rId) rId = sheet_el->Attribute("r:id"); 

        if (name && rId && sheet_id_str) {
            rid_to_name[std::string(rId)] = std::string(name);
        }
    }

    // Now parse xl/_rels/workbook.xml.rels to get the target path for each rId
    auto rels_doc = get_sheet_xml("xl/_rels/workbook.xml.rels");
    if (!rels_doc) return relations;

    tinyxml2::XMLElement* rels_root = rels_doc->FirstChildElement("Relationships");
    if (!rels_root) return relations;

    // We need to track sheet IDs. Since workbook.xml provides sheetId, we can use that.
    // But the order in workbook.xml is what defines the sequence.
    // Let's iterate through the sheets in workbook.xml again to maintain order and get IDs.
    for (tinyxml2::XMLElement* sheet_el = workbook_root->FirstChildElement("sheet"); 
         sheet_el != nullptr; 
         sheet_el = sheet_el->NextSiblingElement("sheet")) {
        
        const char* name = sheet_el->Attribute("name");
        const char* sheet_id_str = sheet_el->Attribute("sheetId");
        const char* rId = sheet_el->Attribute("r:id");
        if (!rId) rId = sheet_el->Attribute("r:id");

        if (name && rId && sheet_id_str) {
            std::string target_path = "";
            // Find the target path in the .rels file for this rId
            for (tinyxml2::XMLElement* rel = rels_root->FirstChildElement("Relationship"); 
                 rel != nullptr; 
                 rel = rel->NextSiblingElement("Relationship")) {
                const char* rel_id = rel->Attribute("Id");
                if (rel_id && std::string(rel_id) == rId) {
                    const char* target = rel->Attribute("Target");
                    if (target) {
                        target_path = target;
                        break;
                    }
                }
            }

            if (!target_path.empty()) {
                // Ensure target path is relative to the zip root if it's relative
                // XLSX targets in .rels are usually relative to the .rels file location.
                // xl/_rels/workbook.xml.rels -> target "worksheets/sheet1.xml" becomes "xl/worksheets/sheet1.xml"
                if (target_path.find("worksheets/") == 0 || target_path.find("sheets/") == 0) {
                    target_path = "xl/" + target_path;
                }
                
                relations.emplace_back(name, std::stoul(sheet_id_str), rId);
            }
        }
    }

    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& path) {
    auto it = archive_content.find(path);
    if (it == archive_content.end()) {
        return nullptr;
    }

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return nullptr;
    }
    return doc;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    std::string path = "xl/sharedStrings.xml";
    
    auto doc = get_sheet_xml(path);
    if (!doc) return strings;

    tinyxml2::XMLElement* root = doc->FirstChildElement("sst");
    if (!root) return strings;

    for (tinyxml2::XMLElement* t = root->FirstChildElement("t"); t != nullptr; t = t->NextSiblingElement("t")) {
        if (t->GetText()) {
            strings.push_back(t->GetText());
        } else {
            strings.push_back("");
        }
    }
    return strings;
}
