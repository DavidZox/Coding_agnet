#include "archive.h"
#include <fstream>
#include <sstream>
#include <miniz.h>
#include <tinyxml2.h>

namespace xlsx2csv {

archive::archive(const std::string& filename) {
    mz_zip_archive zip_archive;
    mz_zip_zero_struct(&zip_archive);

    if (!mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0)) {
        throw std::runtime_error("Failed to open zip archive");
    }

    for (mz_uint i = 0; i < mz_zip_reader_get_num_files(&zip_archive); i++) {
        mz_zip_archive_file_stat file_stat;
        if (!mz_zip_reader_file_stat(&zip_archive, i, &file_stat)) {
            mz_zip_reader_end(&zip_archive);
            throw std::runtime_error("Failed to get file stat");
        }

        void* p = mz_zip_reader_extract_to_heap(&zip_archive, file_stat.m_filename, 0, 0);
        if (!p) {
            mz_zip_reader_end(&zip_archive);
            throw std::runtime_error("Failed to extract file");
        }

        archive_content[file_stat.m_filename] = std::string_view(static_cast<char*>(p), file_stat.m_uncomp_size);
        archive_files.push_back(p);
    }

    mz_zip_reader_end(&zip_archive);
}

std::vector<sheet_desc> archive::get_sheet_relations() const {
    std::vector<sheet_desc> sheet_relations;
    auto it = archive_content.find("xl/workbook.xml");
    if (it == archive_content.end()) {
        throw std::runtime_error("workbook.xml not found");
    }

    tinyxml2::XMLDocument workbook_doc;
    if (workbook_doc.Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        throw std::runtime_error("Failed to parse workbook.xml");
    }

    auto* workbook = workbook_doc.FirstChildElement("workbook");
    if (!workbook) {
        throw std::runtime_error("workbook element not found");
    }

    auto* sheets = workbook->FirstChildElement("sheets");
    if (!sheets) {
        throw std::runtime_error("sheets element not found");
    }

    for (auto* sheet = sheets->FirstChildElement("sheet"); sheet; sheet = sheet->NextSiblingElement("sheet")) {
        const char* name = sheet->Attribute("name");
        const char* sheetId = sheet->Attribute("sheetId");
        const char* rId = sheet->Attribute("r:id");
        if (name && sheetId && rId) {
            sheet_relations.emplace_back(name, static_cast<std::uint32_t>(std::stoi(sheetId)), rId);
        }
    }

    return sheet_relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) const {
    auto it = archive_content.find(sheet_path);
    if (it == archive_content.end()) {
        throw std::runtime_error("Sheet XML not found");
    }

    auto xml_doc = std::make_shared<tinyxml2::XMLDocument>();
    if (xml_doc->Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        throw std::runtime_error("Failed to parse sheet XML");
    }

    return xml_doc;
}

std::vector<std::string> archive::get_shared_strings() const {
    std::vector<std::string> shared_strings;
    auto it = archive_content.find("xl/sharedStrings.xml");
    if (it == archive_content.end()) {
        return shared_strings; // No shared strings
    }

    tinyxml2::XMLDocument shared_strings_doc;
    if (shared_strings_doc.Parse(it->second.data(), it->second.size()) != tinyxml2::XML_SUCCESS) {
        throw std::runtime_error("Failed to parse sharedStrings.xml");
    }

    auto* sst = shared_strings_doc.FirstChildElement("sst");
    if (!sst) {
        throw std::runtime_error("sst element not found");
    }

    for (auto* si = sst->FirstChildElement("si"); si; si = si->NextSiblingElement("si")) {
        auto* t = si->FirstChildElement("t");
        if (t) {
            shared_strings.push_back(t->GetText());
        } else {
            shared_strings.push_back("");
        }
    }

    return shared_strings;
}

archive::~archive() {
    for (void* p : archive_files) {
        mz_free(p);
    }
}

} // namespace xlsx2csv
