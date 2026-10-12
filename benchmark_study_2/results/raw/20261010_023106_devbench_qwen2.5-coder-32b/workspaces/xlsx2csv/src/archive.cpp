#include "archive.h"
#include <fstream>
#include <sstream>
#include <tinyxml2.h>
#include <miniz.h>

namespace {
    std::unordered_map<std::string, std::string> unzip(const std::string& zip_path) {
        std::unordered_map<std::string, std::string> files;
        mz_zip_archive zip_archive;
        memset(&zip_archive, 0, sizeof(zip_archive));

        if (!mz_zip_reader_init_file(&zip_archive, zip_path.c_str(), 0)) {
            return files;
        }

        for (mz_uint i = 0; i < mz_zip_reader_get_num_files(&zip_archive); i++) {
            mz_zip_archive_file_stat file_stat;
            if (!mz_zip_reader_file_stat(&zip_archive, i, &file_stat)) {
                continue;
            }

            mz_uint uncomp_size = 0;
            void* p = mz_zip_reader_extract_to_heap(&zip_archive, i, 0, uncomp_size);
            if (!p) {
                continue;
            }

            files[file_stat.m_filename] = std::string(static_cast<char*>(p), uncomp_size);
            mz_free(p);
        }

        mz_zip_reader_end(&zip_archive);
        return files;
    }
}

archive::archive(const std::string& xlsx_filename) {
    auto unzip_result = unzip(xlsx_filename);
    for (const auto& [filename, content] : unzip_result) {
        archive_content[filename] = std::string_view(content);
        if (filename.find(".xml") != std::string::npos) {
            auto doc = std::make_shared<tinyxml2::XMLDocument>();
            if (doc->Parse(content.c_str(), content.size()) == tinyxml2::XML_SUCCESS) {
                xml_content[filename] = doc;
            }
        }
    }
}

std::vector<sheet_desc> archive::get_sheet_relations() const {
    std::vector<sheet_desc> sheet_relations;
    auto workbook_xml = xml_content.find("[Content_Types].xml");
    if (workbook_xml != xml_content.end()) {
        tinyxml2::XMLElement* root = workbook_xml->second->FirstChildElement("Types");
        if (root) {
            for (tinyxml2::XMLElement* override = root->FirstChildElement("Override"); override; override = override->NextSiblingElement("Override")) {
                const char* partName = override->Attribute("PartName");
                const char* contentType = override->Attribute("ContentType");
                if (partName && contentType && std::string(contentType) == "application/vnd.openxmlformats-package.core-properties+xml") {
                    continue; // Skip core properties
                }
                if (partName && contentType && std::string(contentType) == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml") {
                    std::string workbook_path = partName;
                    workbook_path.erase(0, 1); // Remove leading '/'
                    auto workbook_doc = xml_content.find(workbook_path);
                    if (workbook_doc != xml_content.end()) {
                        tinyxml2::XMLElement* workbook_root = workbook_doc->second->FirstChildElement("workbook");
                        if (workbook_root) {
                            tinyxml2::XMLElement* sheets = workbook_root->FirstChildElement("sheets");
                            if (sheets) {
                                for (tinyxml2::XMLElement* sheet = sheets->FirstChildElement("sheet"); sheet; sheet = sheet->NextSiblingElement("sheet")) {
                                    const char* sheetId = sheet->Attribute("sheetId");
                                    const char* rId = sheet->Attribute("r:id");
                                    const char* name = sheet->Attribute("name");
                                    if (sheetId && rId && name) {
                                        sheet_relations.emplace_back(name, std::stoul(sheetId), rId);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return sheet_relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) const {
    auto it = xml_content.find(sheet_path);
    if (it != xml_content.end()) {
        return it->second;
    }
    return nullptr;
}

std::vector<std::string> archive::get_shared_strings() const {
    std::vector<std::string> shared_strings;
    auto shared_strings_xml = xml_content.find("xl/sharedStrings.xml");
    if (shared_strings_xml != xml_content.end()) {
        tinyxml2::XMLElement* root = shared_strings_xml->second->FirstChildElement("sst");
        if (root) {
            for (tinyxml2::XMLElement* si = root->FirstChildElement("si"); si; si = si->NextSiblingElement("si")) {
                tinyxml2::XMLElement* t = si->FirstChildElement("t");
                if (t) {
                    shared_strings.push_back(t->GetText());
                }
            }
        }
    }
    return shared_strings;
}
