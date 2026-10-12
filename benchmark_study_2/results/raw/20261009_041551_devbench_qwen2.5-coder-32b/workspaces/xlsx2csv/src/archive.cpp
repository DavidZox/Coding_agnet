#include "archive.h"
#include "tinyxml2.h"
#include <miniz.h>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <unordered_map>
#include <memory>
#include <tuple>
#include <algorithm>

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    mz_zip_zero_struct(&zip_archive);

    if (!mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0)) {
        throw std::runtime_error("Failed to open archive");
    }

    for (mz_uint i = 0; i < mz_zip_reader_get_num_files(&zip_archive); ++i) {
        mz_zip_archive_file_stat file_stat;
        if (!mz_zip_reader_file_stat(&zip_archive, i, &file_stat)) {
            mz_zip_reader_end(&zip_archive);
            throw std::runtime_error("Failed to get file stat");
        }

        void* file_data = nullptr;
        size_t file_size = 0;
        if (!mz_zip_reader_extract_to_heap(&zip_archive, i, &file_data, &file_size, 0)) {
            mz_zip_reader_end(&zip_archive);
            throw std::runtime_error("Failed to extract file");
        }

        archive_content[file_stat.m_filename] = std::string_view(static_cast<char*>(file_data), file_size);
        archive_files.push_back(file_data);
    }

    mz_zip_reader_end(&zip_archive);
}

archive::~archive() {
    for (void* file_data : archive_files) {
        mz_free(file_data);
    }
}

std::vector<sheet_desc> archive::get_sheet_relations() const {
    std::vector<sheet_desc> sheet_relations;
    auto it = archive_content.find("xl/workbook.xml");
    if (it == archive_content.end()) {
        throw std::runtime_error("Workbook.xml not found");
    }

    tinyxml2::XMLDocument workbook_xml;
    if (workbook_xml.Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        throw std::runtime_error("Failed to parse workbook.xml");
    }

    tinyxml2::XMLElement* workbook = workbook_xml.FirstChildElement("workbook");
    if (!workbook) {
        throw std::runtime_error("workbook element not found");
    }

    tinyxml2::XMLElement* sheets = workbook->FirstChildElement("sheets");
    if (!sheets) {
        throw std::runtime_error("sheets element not found");
    }

    for (tinyxml2::XMLElement* sheet = sheets->FirstChildElement("sheet"); sheet; sheet = sheet->NextSiblingElement("sheet")) {
        const char* name = sheet->Attribute("name");
        const char* sheetId = sheet->Attribute("sheetId");
        const char* rId = sheet->Attribute("r:id");
        if (name && sheetId && rId) {
            sheet_relations.emplace_back(name, std::stoi(sheetId), rId);
        }
    }

    return sheet_relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) const {
    auto it = archive_content.find(sheet_path);
    if (it == archive_content.end()) {
        throw std::runtime_error("Sheet XML not found");
    }

    std::shared_ptr<tinyxml2::XMLDocument> sheet_xml = std::make_shared<tinyxml2::XMLDocument>();
    if (sheet_xml->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        throw std::runtime_error("Failed to parse sheet XML");
    }

    return sheet_xml;
}

std::vector<std::string> archive::get_shared_strings() const {
    std::vector<std::string> shared_strings;
    auto it = archive_content.find("xl/sharedStrings.xml");
    if (it == archive_content.end()) {
        return shared_strings; // No shared strings
    }

    tinyxml2::XMLDocument shared_strings_xml;
    if (shared_strings_xml.Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        throw std::runtime_error("Failed to parse sharedStrings.xml");
    }

    tinyxml2::XMLElement* sst = shared_strings_xml.FirstChildElement("sst");
    if (!sst) {
        throw std::runtime_error("sst element not found");
    }

    for (tinyxml2::XMLElement* si = sst->FirstChildElement("si"); si; si = si->NextSiblingElement("si")) {
        tinyxml2::XMLElement* t = si->FirstChildElement("t");
        if (t) {
            shared_strings.push_back(t->GetText());
        }
    }

    return shared_strings;
}
