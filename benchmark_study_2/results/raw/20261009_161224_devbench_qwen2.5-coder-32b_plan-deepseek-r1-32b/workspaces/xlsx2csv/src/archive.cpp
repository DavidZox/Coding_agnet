#include "archive.h"
#include "tinyxml2.h"
#include <unordered_map>
#include <vector>
#include <string>
#include <memory>
#include <miniz.h>
#include <iostream>
#include <fstream>
#include <sstream>

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    memset(&zip_archive, 0, sizeof(zip_archive));

    if (!mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0)) {
        throw std::runtime_error("Failed to open archive");
    }

    for (mz_uint i = 0; i < mz_zip_reader_get_num_files(&zip_archive); i++) {
        mz_zip_archive_file_stat file_stat;
        if (!mz_zip_reader_file_stat(&zip_archive, i, &file_stat)) {
            mz_zip_reader_end(&zip_archive);
            throw std::runtime_error("Failed to get file stat");
        }

        void* p = mz_zip_reader_extract_to_heap(&zip_archive, i, 0, 0);
        if (!p) {
            mz_zip_reader_end(&zip_archive);
            throw std::runtime_error("Failed to extract file");
        }

        archive_content[file_stat.m_filename] = std::string_view(static_cast<char*>(p), file_stat.m_uncomp_size);
        archive_files.push_back(p);
    }

    mz_zip_reader_end(&zip_archive);
}

archive::~archive() {
    for (void* p : archive_files) {
        mz_free(p);
    }
}

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    auto it = archive_content.find("xl/workbook.xml");
    if (it == archive_content.end()) {
        throw std::runtime_error("workbook.xml not found");
    }

    tinyxml2::XMLDocument doc;
    doc.Parse(it->second.data(), it->second.size());
    tinyxml2::XMLElement* root = doc.RootElement();
    tinyxml2::XMLElement* sheets = root->FirstChildElement("sheets");
    if (!sheets) {
        throw std::runtime_error("sheets element not found");
    }
    for (tinyxml2::XMLElement* sheet = sheets->FirstChildElement("sheet"); sheet != nullptr; sheet = sheet->NextSiblingElement("sheet")) {
        const char* name = sheet->Attribute("name");
        const char* sheetId = sheet->Attribute("sheetId");
        const char* rId = sheet->Attribute("r:id");
        relations.emplace_back(name, std::stoi(sheetId), rId);
    }

    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) {
    auto it = archive_content.find(sheet_path);
    if (it == archive_content.end()) {
        throw std::runtime_error("Sheet XML not found");
    }

    std::shared_ptr<tinyxml2::XMLDocument> doc = std::make_shared<tinyxml2::XMLDocument>();
    doc->Parse(it->second.data(), it->second.size());
    return doc;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> shared_strings;
    auto it = archive_content.find("xl/sharedStrings.xml");
    if (it == archive_content.end()) {
        return shared_strings;
    }

    tinyxml2::XMLDocument doc;
    doc.Parse(it->second.data(), it->second.size());
    tinyxml2::XMLElement* root = doc.RootElement();
    for (tinyxml2::XMLElement* sst = root->FirstChildElement("sst"); sst != nullptr; sst = sst->NextSiblingElement("sst")) {
        for (tinyxml2::XMLElement* si = sst->FirstChildElement("si"); si != nullptr; si = si->NextSiblingElement("si")) {
            for (tinyxml2::XMLElement* t = si->FirstChildElement("t"); t != nullptr; t = t->NextSiblingElement("t")) {
                shared_strings.push_back(t->GetText());
            }
        }
    }

    return shared_strings;
}
