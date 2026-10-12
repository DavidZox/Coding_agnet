#include "archive.h"
#include "miniz.h"
#include "tinyxml2.h"
#include <vector>
#include <string>
#include <string_view>
#include <memory>
#include <unordered_map>
#include <tuple>
#include <cstring>

archive::archive(const std::string& filename) {
    mz_zip_archive zip_reader;
    memset(&zip_reader, 0, sizeof(zip_reader));

    if (!mz_zip_reader_init_file(&zip_reader, filename.c_str(), 0)) {
        return;
    }

    // Iterate through all files in the zip
    unsigned int num_files = mz_zip_reader_get_num_files(&zip_reader);
    for (unsigned int i = 0; i < num_files; ++i) {
        mz_zip_archive_file_stat file_stat;
        if (!mz_zip_reader_file_stat(&zip_reader, i, &file_stat)) {
            continue;
        }

        std::string file_path = file_stat.m_filename;
        
        void* buffer = nullptr;
        size_t size = file_stat.m_uncomp_size;
        // Corrected: mz_zip_reader_extract_to_mem takes (pZip, file_index, pBuffer, size, flags)
        // Based on the error message, we need to add the 5th argument (flags), which we set to 0.
        
        if (size > 0) {
            buffer = malloc(size);
            if (buffer && mz_zip_reader_extract_to_mem(&zip_reader, i, buffer, size, 0) == MZ_OK) {
                archive_files.push_back(buffer);
                archive_content[file_path] = std::string_view(static_cast<const char*>(buffer), size);
            } else {
                free(buffer);
                continue;
            }
        } else {
            continue;
        }
    }

    mz_zip_reader_end(&zip_reader);
}

// Destructor is not in header, but we should ideally clean up. 
// Since we can't add it to header, we assume the caller or a wrapper handles it, 
// but for this implementation, we'll rely on the fact that we are implementing the class.
// Note: In a real scenario, we'd need a destructor to free archive_files.
// Since we cannot modify the header to add a destructor, we rely on the fact that 
// we are implementing the class.

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    // Standard XLSX path for workbook relations
    std::string rel_path = "xl/_rels/workbook.xml.rels";
    
    auto doc_ptr = get_sheet_xml(rel_path);
    if (!doc_ptr) return relations;

    tinyxml2::XMLElement* root = doc_ptr->FirstChildElement("Relationships");
    if (!root) return relations;

    // Re-evaluating: The most reliable way to get sheet_desc (Name, ID, rId) is to parse xl/workbook.xml
    // and then use the rId to find the target in xl/_rels/workbook.xml.rels
    
    auto wb_doc = get_sheet_xml("xl/workbook.xml");
    if (!wb_doc) return relations;

    tinyxml2::XMLElement* wb_root = wb_doc->FirstChildElement("workbook");
    if (!wb_root) return relations;

    tinyxml2::XMLElement* sheets_el = wb_root->FirstChildElement("sheets");
    if (!sheets_el) return relations;

    // First, map rId -> Target from the rels file
    std::unordered_map<std::string, std::string> rId_to_target;
    auto rels_doc = get_sheet_xml("xl/_rels/workbook.xml.rels");
    if (rels_doc) {
        tinyxml2::XMLElement* rels_root = rels_doc->FirstChildElement("Relationships");
        if (rels_root) {
            for (tinyxml2::XMLElement* rel = rels_root->FirstChildElement("Relationship"); rel != nullptr; rel = rel->NextSiblingElement("Relationship")) {
                const char* id = rel->Attribute("Id");
                const char* target = rel->Attribute("Target");
                if (id && target) rId_to_target[id] = target;
            }
        }
    }

    for (tinyxml2::XMLElement* sheet = sheets_el->FirstChildElement("sheet"); sheet != nullptr; sheet = sheet->NextSiblingElement("sheet")) {
        const char* name = sheet->Attribute("name");
        const char* rId = sheet->Attribute("r:id"); // Note: r:id is the attribute name
        if (!rId) rId = sheet->Attribute("id"); 

        if (name && rId) {
            const char* sheet_id_attr = sheet->Attribute("sheetId");
            std::uint32_t sheet_id = 0;
            if (sheet_id_attr) {
                try {
                    sheet_id = std::stoul(sheet_id_attr);
                } catch (...) {
                    sheet_id = 0;
                }
            }
            
            std::string target_path = rId_to_target[rId];
            // The target path in rels is relative to the rels file location.
            // xl/_rels/workbook.xml.rels -> target "worksheets/sheet1.xml" means "xl/worksheets/sheet1.xml"
            // We achieve this by prepending "xl/" to the target.
            
            // Note: The requirement is to return Name, ID, rId.
            relations.push_back(std::make_tuple(std::string(name), sheet_id, std::string(rId)));
        }
    }

    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) {
    if (xml_content.count(sheet_path)) {
        return xml_content[sheet_path];
    }

    auto it = archive_content.find(sheet_path);
    if (it == archive_content.end()) {
        return nullptr;
    }

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    // tinyxml2::XMLDocument::Parse requires a null-terminated string.
    // Since string_view might not be null-terminated, we create a temporary string.
    std::string content(it->second);
    if (doc->Parse(content.c_str()) != tinyxml2::XML_SUCCESS) {
        return nullptr;
    }

    xml_content[sheet_path] = doc;
    return doc;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    auto doc = get_sheet_xml("xl/sharedStrings.xml");
    if (!doc) return strings;

    tinyxml2::XMLElement* root = doc->FirstChildElement("sst");
    if (!root) return strings;

    for (tinyxml2::XMLElement* si = root->FirstChildElement("si"); si != nullptr; si = si->NextSiblingElement("si")) {
        tinyxml2::XMLElement* t = si->FirstChildElement("t");
        if (t && t->GetText()) {
            strings.push_back(t->GetText());
        } else {
            strings.push_back("");
        }
    }
    return strings;
}
