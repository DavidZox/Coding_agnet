#include "archive.h"
#include "miniz.h"
#include "tinyxml2.h"
#include <vector>
#include <string>
#include <memory>
#include <unordered_map>
#include <tuple>
#include <cstring>
#include <sstream>

namespace my_xlsx {
namespace xlsx_reader {

// Helper function to resolve relative paths in XLSX
std::string resolve_relative_path(const std::string& base_dir, const std::string& target) {
    if (target.empty()) return "";
    
    // If target is absolute (starts with /), it's relative to the zip root
    if (target[0] == '/') {
        std::string res = target;
        if (res.length() > 1 && res[1] == '/') res = res.substr(1);
        // Remove leading slash for consistency
        if (!res.empty() && res[0] == '/') res = res.substr(1);
        return res;
    }

    // Split base_dir into components
    std::vector<std::string> base_parts;
    std::stringstream ss_base(base_dir);
    std::string item;
    while (std::getline(ss_base, item, '/')) {
        if (!item.empty()) base_parts.push_back(item);
    }

    // Split target into components
    std::vector<std::string> target_parts;
    std::stringstream ss_target(target);
    while (std::getline(ss_target, item, '/')) {
        if (!item.empty()) target_parts.push_back(item);
    }

    // Process target parts against base_parts
    for (const auto& part : target_parts) {
        if (part == ".") {
            continue;
        } else if (part == "..") {
            if (!base_parts.empty()) {
                base_parts.pop_back();
            }
        } else {
            base_parts.push_back(part);
        }
    }

    // Reconstruct path
    std::string result;
    for (size_t i = 0; i < base_parts.size(); ++i) {
        result += base_parts[i];
        if (i < base_parts.size() - 1) {
            result += "/";
        }
    }
    return result;
}

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    memset(&zip_archive, 0, sizeof(zip_archive));

    if (mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0) != MZ_OK) {
        return;
    }

    // To keep string_view valid, we store actual strings in a vector
    // We'll store the pointer to this vector in archive_files[0]
    auto contents_ptr = new std::vector<std::string>();
    archive_files.push_back(static_cast<void*>(contents_ptr));

    mz_uint file_count = mz_zip_reader_get_num_files(&zip_archive);
    for (mz_uint i = 0; i < file_count; ++i) {
        mz_zip_archive_file_stat file_info;
        if (mz_zip_reader_file_stat(&zip_archive, i, &file_info) == MZ_OK) {
            std::string file_path(reinterpret_cast<const char*>(file_info.m_filename));
            
            // Ensure file_path doesn't have a leading slash for consistent key lookup
            if (!file_path.empty() && file_path[0] == '/') {
                file_path = file_path.substr(1);
            }
            
            // Get file content
            mz_ulong uncompressed_size = file_info.m_uncomp_size;
            void* pContent = nullptr;
            
            if (mz_zip_reader_extract_to_mem(&zip_archive, i, &pContent, static_cast<size_t>(uncompressed_size), MZ_DEFAULT_COMPRESSION) == MZ_OK) {
                // Convert the raw buffer to std::string to own the data
                std::string content(static_cast<const char*>(pContent), static_cast<size_t>(uncompressed_size));
                mz_free(pContent);
                
                (*contents_ptr).push_back(std::move(content));
                
                // The last added string in the vector is the one we want
                archive_content[file_path] = (*contents_ptr).back();
            }
        }
    }

    // Close the zip archive
    mz_zip_reader_end(&zip_archive);

    // Build r_id_to_path mapping from xl/_rels/workbook.xml.rels
    std::string rels_path = "xl/_rels/workbook.xml.rels";
    auto it_rels = archive_content.find(rels_path);
    if (it_rels != archive_content.end()) {
        auto doc = std::make_shared<tinyxml2::XMLDocument>();
        if (doc->Parse(it_rels->second.data(), it_rels->second.size()) == tinyxml2::XML_SUCCESS) {
            tinyxml2::XMLElement* root = doc->FirstChildElement("Relationships");
            if (root) {
                // Determine the base directory for resolving relative paths.
                // The rels file is in "xl/_rels/". The targets are relative to "xl/".
                // So we need to go up one level from "xl/_rels/" to "xl/".
                std::string base_dir_for_resolution = "xl";

                for (tinyxml2::XMLElement* elem = root->FirstChildElement("Relationship");
                     elem != nullptr;
                     elem = elem->NextSiblingElement("Relationship")) {
                    const char* r_id = elem->Attribute("Id");
                    const char* target = elem->Attribute("Target");
                    if (r_id && target) {
                        std::string target_str(target);
                        // Resolve target relative to the directory containing the rels file
                        // Since rels is in xl/_rels/, and targets are relative to xl/,
                        // we use "xl" as the base.
                        std::string resolved = resolve_relative_path(base_dir_for_resolution, target_str);
                        // Ensure resolved path doesn't have a leading slash
                        if (!resolved.empty() && resolved[0] == '/') {
                            resolved = resolved.substr(1);
                        }
                        r_id_to_path[r_id] = resolved;
                    }
                }
            }
        }
    }
}

// Note: The destructor is not defined in the header, but for a complete implementation 
// we should ideally clean up archive_files. Since I can only output archive.cpp, 
// I assume the caller (or a destructor if added) handles it.

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    
    // XLSX structure: sheet information (name, sheetId, rId) is in xl/workbook.xml
    // However, the relations are actually defined in xl/_rels/workbook.xml.rels
    // But the sheet names and IDs are in xl/workbook.xml.
    // Let's check xl/workbook.xml first for sheet definitions.
    std::string workbook_xml_path = "xl/workbook.xml";
    auto wb_it = archive_content.find(workbook_xml_path);
    if (wb_it != archive_content.end()) {
        auto doc = get_sheet_xml(workbook_xml_path);
        if (doc) {
            tinyxml2::XMLElement* root = doc->RootElement();
            if (root) {
                for (tinyxml2::XMLElement* elem = root->FirstChildElement("sheet"); 
                     elem != nullptr; 
                     elem = elem->NextSiblingElement("sheet")) {
                    
                    const char* name = elem->Attribute("name");
                    const char* sheet_id_str = elem->Attribute("sheetId");
                    const char* r_id = elem->Attribute("rId");
                    
                    if (name && sheet_id_str && r_id) {
                        std::string sheet_name(name);
                        std::uint32_t sheet_id = static_cast<std::uint32_t>(std::stoul(sheet_id_str));
                        std::string relation_id(r_id);
                        
                        relations.emplace_back(sheet_name, sheet_id, relation_id);
                    }
                }
            }
        }
    }
    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& path) {
    std::string actual_path = path;
    // If the path is an rId, resolve it using r_id_to_path
    if (r_id_to_path.count(path)) {
        actual_path = r_id_to_path[path];
    }

    // Ensure path doesn't have a leading slash if it's not meant to be absolute
    if (!actual_path.empty() && actual_path[0] == '/') {
        actual_path = actual_path.substr(1);
    }

    auto it = archive_content.find(actual_path);
    if (it != archive_content.end()) {
        auto doc = std::make_shared<tinyxml2::XMLDocument>();
        // Use Parse with size to ensure it handles non-null-terminated string_view correctly
        if (doc->Parse(it->second.data(), it->second.size()) == tinyxml2::XML_SUCCESS) {
            xml_content[actual_path] = doc;
            return doc;
        }
    }
    return nullptr;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    std::string path = "xl/sharedStrings.xml";
    
    auto doc = get_sheet_xml(path);
    if (doc) {
        tinyxml2::XMLElement* root = doc->RootElement();
        if (root) {
            for (tinyxml2::XMLElement* elem = root->FirstChildElement("si"); 
                 elem != nullptr; 
                 elem = elem->NextSiblingElement("si")) {
                // In XLSX sharedStrings.xml, the actual text is stored in the <v> tag
                // or sometimes in a <t> tag depending on the version.
                tinyxml2::XMLElement* v_elem = elem->FirstChildElement("v");
                if (!v_elem) {
                    v_elem = elem->FirstChildElement("t");
                }
                
                if (v_elem && v_elem->GetText()) {
                    strings.push_back(v_elem->GetText());
                } else {
                    strings.push_back("");
                }
            }
        }
    }
    return strings;
}

} // namespace xlsx_reader
} // namespace my_xlsx
