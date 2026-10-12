#include "archive.h"
#include "miniz.h"
#include "tinyxml2.h"
#include <vector>
#include <string>
#include <memory>
#include <unordered_map>
#include <tuple>
#include <cstring>

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    memset(&zip_archive, 0, sizeof(zip_archive));

    if (mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0) != MZ_OK) {
        return;
    }

    // Iterate through all files in the zip
    mz_uint num_files = mz_zip_reader_get_num_files(&zip_archive);
    for (mz_uint i = 0; i < num_files; ++i) {
        mz_zip_archive_file_stat file_stat;
        if (mz_zip_reader_file_stat(&zip_archive, i, &file_stat) != MZ_OK) {
            continue;
        }

        std::string file_path = file_stat.m_filename;
        
        // Allocate buffer for file content
        void* buffer = nullptr;
        size_t file_size = 0;
        buffer = mz_zip_reader_extract_to_heap(&zip_archive, i, &file_size, 0);
        if (!buffer) {
            continue;
        }

        // Store the buffer in archive_files to manage lifetime
        archive_files.push_back(buffer);
        
        // Store string_view pointing to the buffer
        // We use a vector of strings to ensure the memory is managed and valid for string_view
        // However, since we are using archive_files (malloc'd buffers), we can point directly to them.
        // To ensure the string_view is safe, we must ensure the buffer is not freed while archive exists.
        archive_content[file_path] = std::string_view(static_cast<const char*>(buffer), file_size);
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
    
    // 1. Parse xl/workbook.xml to get sheet names and rIds
    std::string workbook_xml_path = "xl/workbook.xml";
    auto workbook_doc_ptr = get_sheet_xml(workbook_xml_path);
    if (!workbook_doc_ptr) return relations;

    std::unordered_map<std::string, std::string> rId_to_name;
    tinyxml2::XMLElement* root = workbook_doc_ptr->FirstChildElement("workbook");
    if (root) {
        for (tinyxml2::XMLElement* sheet = root->FirstChildElement("sheet"); sheet != nullptr; sheet = sheet->NextSiblingElement("sheet")) {
            const char* name = sheet->Attribute("name");
            const char* rId = sheet->Attribute("r:id");
            if (name && rId) {
                rId_to_name[rId] = name;
            }
        }
    }

    // 2. Parse xl/worksheets/_rels/workbook.xml.rels to get Target paths
    std::string rels_path = "xl/worksheets/_rels/workbook.xml.rels";
    auto rels_doc_ptr = get_sheet_xml(rels_path);
    if (!rels_doc_ptr) return relations;

    tinyxml2::XMLElement* rel_root = rels_doc_ptr->FirstChildElement("Relationships");
    if (rel_root) {
        uint32_t id_counter = 1;
        for (tinyxml2::XMLElement* rel = rel_root->FirstChildElement("Relationship"); rel != nullptr; rel = rel->NextSiblingElement("Relationship")) {
            const char* rId = rel->Attribute("Id");
            const char* target = rel->Attribute("Target");
            if (rId && target && rId_to_name.count(rId)) {
                // sheet_desc: (name, id, rId)
                // Note: The UML says id is uint32_t. We'll use a placeholder or parse if available.
                // Since the requirement doesn't specify how to get the numeric ID from rId, 
                // we'll treat the sequence as the ID or use a counter.
                // However, looking at the sequence, the workbook handles the mapping.
                // Let's assume the ID is just a sequence or we need to find it.
                // Actually, the sheet_desc is (name, id, rId).
                // Let's use a simple counter for the ID part.
                relations.emplace_back(rId_to_name[rId], id_counter++, target);
            }
        }
    }

    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& path) {
    if (xml_content.count(path)) {
        return xml_content[path];
    }

    auto it = archive_content.find(path);
    if (it == archive_content.end()) {
        return nullptr;
    }

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    // tinyxml2::XMLDocument::Parse requires a null-terminated string.
    // Since our buffer is from malloc, it should be null-terminated if the zip tool added it,
    // but to be safe, we create a temporary string.
    std::string xml_str(it->second);
    if (doc->Parse(xml_str.c_str()) != tinyxml2::XML_SUCCESS) {
        return nullptr;
    }

    xml_content[path] = doc;
    return doc;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> shared_strings;
    std::string path = "xl/sharedStrings.xml";
    
    auto doc_ptr = get_sheet_xml(path);
    if (!doc_ptr) return shared_strings;

    tinyxml2::XMLElement* root = doc_ptr->FirstChildElement("sst");
    if (root) {
        for (tinyxml2::XMLElement* si = root->FirstChildElement("si"); si != nullptr; si = si->NextSiblingElement("si")) {
            tinyxml2::XMLElement* t = si->FirstChildElement("t");
            if (t && t->GetText()) {
                shared_strings.push_back(t->GetText());
            } else {
                shared_strings.push_back("");
            }
        }
    }
    return shared_strings;
}
