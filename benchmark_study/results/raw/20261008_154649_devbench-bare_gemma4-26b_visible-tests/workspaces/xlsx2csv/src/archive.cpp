#include "archive.h"
#include "miniz.h"
#include <stdexcept>
#include <iostream>

namespace my_xlsx::xlsx_reader {

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    memset(&zip_archive, 0, sizeof(zip_archive));

    if (!mz_zip_archive_init_file(&zip_archive, filename.c_str(), 0)) {
        throw std::runtime_error("Failed to initialize zip archive");
    }

    mz_uint32 file_count = mz_zip_archive_get_num_files(&zip_archive);
    for (mz_uint32 i = 0; i < file_count; ++i) {
        mz_zip_archive_file_stat file_stat;
        if (mz_zip_archive_get_file_stat(&zip_archive, i, &file_stat)) {
            // We need to keep the buffer alive, so we'll store it in a way that's managed.
            // For this implementation, we'll use a simple approach: 
            // Since we can't easily store string_view pointing to heap without a manager,
            // we'll allocate memory for each file content.
            // However, to strictly follow the UML/Architecture which uses std::string_view,
            // we must ensure the underlying data persists.
            
            // In a real production environment, we'd use a buffer pool.
            // Here, we'll use a trick: we'll store the raw data in a vector of strings 
            // to ensure lifetime, but the UML asks for archive_files as vector<void*>.
            // To satisfy the requirement of the class members:
            
            void* buffer = nullptr;
            mz_uint32 uncompressed_size = 0;
            if (mz_zip_archive_extract_file_to_heap(&zip_archive, file_stat.filename, &buffer, &uncompressed_size, 0)) {
                std::string path(file_stat.filename);
                // We use a hack to store the pointer in archive_files to manage lifetime
                // and use the string_view to point to it.
                // Note: This is a simplified way to manage memory for the purpose of this task.
                archive_files.push_back(buffer); 
                archive_content[path] = std::string_view(static_cast<const char*>(buffer), uncompressed_size);
            }
        }
    }
    // Note: mz_zip_archive_finalize is not needed if we handle memory manually, 
    // but we must close the archive.
    mz_zip_archive_end(&zip_archive);
}

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    auto it = archive_content.find("xl/_rels/workbook.xml.rels");
    if (it == archive_content.end()) return relations;

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return relations;
    }

    tinyxml2::XMLElement* root = doc->FirstChildElement("Relationships");
    if (!root) return relations;

    for (tinyxml2::XMLElement* rel = root->FirstChildElement("Relationship"); rel != nullptr; rel = rel->NextSiblingElement("Relationship")) {
        const char* target = rel->Attribute("Target");
        const char* id = rel->Attribute("Id");
        if (target && id) {
            // In XLSX, sheet relations are usually in xl/worksheets/_rels/workbook.xml.rels
            // or xl/_rels/workbook.xml.rels. The target might be "worksheets/sheet1.xml"
            // We need to resolve the path relative to "xl/".
            std::string rel_id(id);
            std::string target_path = "xl/" + std::string(target);
            
            // We need the sheet name. The sheet name is usually in xl/workbook.xml
            // But the UML says sheet_desc is (name, id, rId).
            // To get the name, we'd need to parse xl/workbook.xml.
            // However, the sequence diagram shows Workbook calls get_sheet_relations.
            // Let's assume we find the name from the workbook.xml or just use the rId for now
            // if the name isn't directly in the rels file.
            // Actually, the sheet name is in xl/workbook.xml, not in the .rels file.
            // But the requirement says get_sheet_relations returns vector<sheet_desc>.
            // Let's parse xl/workbook.xml to get the mapping of rId to name.
            
            // For the sake of this implementation, we will look for the sheet name 
            // by parsing xl/workbook.xml inside this function or assume it's provided.
            // Since we can't easily do two-pass here without complexity, 
            // we'll look for the sheet name in the workbook.xml.
        }
    }
    
    // Correct approach: Parse xl/workbook.xml to get names and rIds, 
    // then use those rIds to find targets in xl/_rels/workbook.xml.rels
    
    auto wb_it = archive_content.find("xl/workbook.xml");
    if (wb_it == archive_content.end()) return relations;

    auto wb_doc = std::make_shared<tinyxml2::XMLDocument>();
    wb_doc->Parse(wb_it->second.data(), wb_it->second.size());
    tinyxml2::XMLElement* wb_root = wb_doc->FirstChildElement("workbook");
    if (!wb_root) return relations;

    tinyxml2::XMLElement* sheets_el = wb_root->FirstChildElement("sheets");
    if (!sheets_el) return relations;

    // Map rId -> target path from .rels
    std::unordered_map<std::string, std::string> r_id_to_target;
    auto rels_it = archive_content.find("xl/_rels/workbook.xml.rels");
    if (rels_it != archive_content.end()) {
        auto rels_doc = std::make_shared<tinyxml2::XMLDocument>();
        rels_doc->Parse(rels_it->second.data(), rels_it->second.size());
        tinyxml2::XMLElement* rels_root = rels_doc->FirstChildElement("Relationships");
        if (rels_root) {
            for (tinyxml2::XMLElement* rel = rels_root->FirstChildElement("Relationship"); rel != nullptr; rel = rel->NextSiblingElement("Relationship")) {
                const char* target = rel->Attribute("Target");
                const char* id = rel->Attribute("Id");
                if (target && id) {
                    r_id_to_target[id] = "xl/" + std::string(target);
                }
            }
        }
    }

    std::uint32_t sheet_id_counter = 1;
    for (tinyxml2::XMLElement* sheet = sheets_el->FirstChildElement("sheet"); sheet != nullptr; sheet = sheet->NextSiblingElement("sheet")) {
        const char* name = sheet->Attribute("name");
        const char* r_id = sheet->Attribute("rId");
        if (name && r_id) {
            std::string target_path = r_id_to_target[r_id];
            relations.push_back(std::make_tuple(std::string(name), sheet_id_counter++, target_path));
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
    if (doc->Parse(it->second.data(), it->second.size()) == tinyxml2::XML_SUCCESS) {
        xml_content[sheet_path] = doc;
        return doc;
    }

    return nullptr;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    // Shared strings are usually in xl/sharedStrings.xml
    auto it = archive_content.find("xl/sharedStrings.xml");
    if (it == archive_content.end()) {
        return strings;
    }

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return strings;
    }

    tinyxml2::XMLElement* root = doc->FirstChildElement("sst");
    if (!root) return strings;

    for (tinyxml2::XMLElement* t = root->FirstChildElement("t"); t != nullptr; t = t->NextSiblingElement("t")) {
        const char* text = t->GetText();
        strings.push_back(text ? std::string(text) : "");
    }

    return strings;
}

} // namespace my_xlsx::xlsx_reader
