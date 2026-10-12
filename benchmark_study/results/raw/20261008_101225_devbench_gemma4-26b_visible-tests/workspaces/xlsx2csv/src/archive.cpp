#include "archive.h"
#include <iostream>
#include <vector>
#include <string>
#include <stdexcept>
#include <map>

namespace my_xlsx::xlsx_reader {

// Internal storage to keep the raw data alive for string_view in archive_content
// Using std::map<std::string, std::string> to ensure stable memory addresses for string_view
static std::map<std::string, std::string> g_data_storage;

archive::archive(const std::string& filename) {
    mz_zip_zero_struct(&zip_archive);
    if (!mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0)) {
        throw std::runtime_error("Failed to initialize zip archive");
    }
}

archive::~archive() {
    mz_zip_reader_end(&zip_archive);
}

bool archive::load_file_to_content(const std::string& filename, const std::string& file_in_zip) {
    size_t file_size = 0;
    void* file_data = mz_zip_reader_extract_file_to_heap(&zip_archive, file_in_zip.c_str(), &file_size, 0);
    
    if (!file_data) {
        return false;
    }

    // Store in map. We need to keep the buffer alive. 
    // Since archive_content uses string_view, we must own the actual string data.
    // To satisfy the header's design, we'll use a static map to hold the data for the lifetime of the program.
    g_data_storage[file_in_zip] = std::string(static_cast<char*>(file_data), file_size);
    archive_content[file_in_zip] = std::string_view(g_data_storage[file_in_zip]);
    
    // Free the heap memory allocated by mz_zip_reader_extract_file_to_heap
    mz_free(file_data);
    
    return true;
}

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    mz_zip_archive* zip = &zip_archive;

    // 1. Load xl/workbook.xml to get sheet names and rIds
    std::string wb_path = "xl/workbook.xml";
    if (!load_file_to_content(wb_path, wb_path)) return relations;
    
    auto wb_doc = std::make_shared<tinyxml2::XMLDocument>();
    wb_doc->Parse(archive_content[wb_path].data(), archive_content[wb_path].size());
    tinyxml2::XMLElement* wb_root = wb_doc->FirstChildElement("workbook");
    if (!wb_root) return relations;

    // 2. Load xl/_rels/workbook.xml.rels to map rId to target path
    std::string rel_path = "xl/_rels/workbook.xml.rels";
    if (!load_file_to_content(rel_path, rel_path)) return relations;
    
    auto rel_doc = std::make_shared<tinyxml2::XMLDocument>();
    rel_doc->Parse(archive_content[rel_path].data(), archive_content[rel_path].size());
    tinyxml2::XMLElement* rel_root = rel_doc->FirstChildElement("Relationships");
    if (!rel_root) return relations;

    std::unordered_map<std::string, std::string> rId_to_target;
    for (tinyxml2::XMLElement* rel = rel_root->FirstChildElement("Relationship"); rel != nullptr; rel = rel->NextSiblingElement("Relationship")) {
        const char* id = rel->Attribute("Id");
        const char* target = rel->Attribute("Target");
        if (id && target) {
            std::string t(target);
            // Targets in rels are often relative, e.g., "worksheets/sheet1.xml"
            // If it starts with a dot, we might need to handle it, but usually it's relative to the rel file.
            // The rel file is in xl/_rels/, so target "worksheets/sheet1.xml" means "xl/worksheets/sheet1.xml"
            if (t.find("../") == 0) {
                t = t.substr(3); // "../worksheets/sheet1.xml" -> "worksheets/sheet1.xml"
            }
            
            // Check if target already starts with "xl/" to avoid "xl/xl/..."
            if (t.find("xl/") == 0) {
                rId_to_target[id] = t;
            } else {
                rId_to_target[id] = "xl/" + t;
            }
        }
    }

    // 3. Combine sheet names from workbook.xml with targets from rels
    int sheet_id_counter = 1;
    for (tinyxml2::XMLElement* sheet = wb_root->FirstChildElement("sheet"); sheet != nullptr; sheet = sheet->NextSiblingElement("sheet")) {
        const char* name = sheet->Attribute("name");
        std::string rid_str;
        
        // Try to find the attribute manually if r:id is tricky
        for (const tinyxml2::XMLAttribute* attr = sheet->FirstAttribute(); attr; attr = attr->Next()) {
            std::string attr_name(attr->Name());
            if (attr_name == "r:id" || attr_name == "id") {
                rid_str = attr->Value();
                break;
            }
        }
        
        if (name && !rid_str.empty() && rId_to_target.count(rid_str)) {
            relations.push_back(std::make_tuple(std::string(name), (std::uint32_t)sheet_id_counter++, rId_to_target[rid_str]));
        }
    }

    return relations; 
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) {
    if (xml_content.count(sheet_path)) {
        return xml_content[sheet_path];
    }

    if (!load_file_to_content(sheet_path, sheet_path)) {
        return nullptr;
    }

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(archive_content[sheet_path].data(), archive_content[sheet_path].size()) != tinyxml2::XML_SUCCESS) {
        return nullptr;
    }

    xml_content[sheet_path] = doc;
    return doc;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    std::string ss_path = "xl/sharedStrings.xml";

    if (!load_file_to_content(ss_path, ss_path)) {
        return strings;
    }

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    doc->Parse(archive_content[ss_path].data(), archive_content[ss_path].size());

    tinyxml2::XMLElement* root = doc->FirstChildElement("sst");
    if (!root) return strings;

    for (tinyxml2::XMLElement* si = root->FirstChildElement("t"); si != nullptr; si = si->NextSiblingElement("t")) {
        if (si->GetText()) {
            strings.push_back(si->GetText());
        } else {
            strings.push_back("");
        }
    }

    return strings;
}

} // namespace my_xlsx::xlsx_reader
