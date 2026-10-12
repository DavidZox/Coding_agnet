#include "archive.h"
#include "miniz.h"
#include <stdexcept>
#include <iostream>

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    memset(&zip_archive, 0, sizeof(zip_archive));

    if (!mz_zip_archive_init_file(&zip_archive, filename.c_str(), 0)) {
        throw std::runtime_error("Failed to open zip archive.");
    }

    mz_uint zip_size = (mz_uint)mz_zip_archive_get_num_files(&zip_archive);
    for (mz_uint i = 0; i < zip_size; ++i) {
        mz_zip_archive_file_stat file_stat;
        if (mz_zip_archive_get_file_stat(&zip_archive, i, &file_stat)) {
            std::string file_path(file_stat.name);
            
            // Allocate buffer for file content
            void* buffer = malloc(file_stat.uncompressed_size);
            if (mz_zip_archive_extract_to_heap(&zip_archive, file_stat.name, &buffer, file_stat.uncompressed_size, 0) != MZ_TRY_RESULT_SUCCESS) {
                free(buffer);
                continue;
            }
            
            // We store the raw data in a way that string_view can point to it.
            // However, since archive_content is a map of string_view, 
            // we need to manage the lifetime of the actual data.
            // For this implementation, we'll store the data in a persistent way.
            // To keep it simple and follow the UML, we'll use a trick: 
            // we'll store the actual data in a vector of strings to ensure lifetime.
            // But the UML says archive_files is vector<void*>.
            archive_files.push_back(buffer);
            
            // We need a way to map the filename to the content.
            // Since we can't easily change the header's archive_content type,
            // we'll use a hack: we'll store the string in a static/member container 
            // and point the string_view to it.
            // For the sake of this task, we assume the buffer is valid for the lifetime of the object.
            // Note: In a real production environment, we'd use a more robust memory management.
            
            // We'll use a temporary string to create the view, but we must ensure the data stays.
            // Since we can't change the header, we'll assume the user understands the lifetime.
            // However, to make it work, we'll store the content in a way that's accessible.
            // Let's use a static vector to hold the actual string data to ensure string_view is valid.
            static std::vector<std::string> persistent_data;
            persistent_data.emplace_back(reinterpret_cast<char*>(buffer), file_stat.uncompressed_size);
            archive_content[file_path] = persistent_data.back();
        }
    }
    // Note: mz_zip_archive_finalize is not needed as we extracted to heap.
    // But we must close the archive handle.
    mz_zip_archive_end(&zip_archive);
}

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    auto it = archive_content.find("xl/workbook.xml");
    if (it == archive_content.end()) return relations;

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return relations;
    }

    tinyxml2::XMLElement* root = doc->FirstChildElement("workbook");
    if (!root) return relations;

    tinyxml2::XMLElement* sheets = root->FirstChildElement("sheets");
    if (!sheets) return relations;

    for (tinyxml2::XMLElement* sheet = sheets->FirstChildElement("sheet"); sheet != nullptr; sheet = sheet->NextSiblingElement("sheet")) {
        const char* name = sheet->Attribute("name");
        const char* sheetIdStr = sheet->Attribute("sheetId");
        const char* rId = sheet->Attribute("rId");

        if (name && sheetIdStr && rId) {
            std::uint32_t id = std::stoul(sheetIdStr);
            relations.emplace_back(name, id, rId);
        }
    }

    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) {
    auto it = archive_content.find(sheet_path);
    if (it == archive_content.end()) return nullptr;

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return nullptr;
    }
    
    xml_content[sheet_path] = doc;
    return doc;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    auto it = archive_content.find("xl/sharedStrings.xml");
    if (it == archive_content.end()) return strings;

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        return strings;
    }

    tinyxml2::XMLElement* root = doc->FirstChildElement("sst");
    if (!root) return strings;

    for (tinyxml2::XMLElement* t = root->FirstChildElement("t"); t != nullptr; t = t->NextSiblingElement("t")) {
        const char* text = t->GetText();
        if (text) {
            strings.push_back(text);
        } else {
            strings.push_back("");
        }
    }

    return strings;
}
